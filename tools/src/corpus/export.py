"""Single-record portable export (spec §10) — the surface-materialization contract.

`export_record` renders one record's content zone to a self-contained folder: an `.md`
file (always), optionally a `.typ` Typst source and a compiled `.pdf` (`corpus.typeset`).
Every addressed surface a segment places (an `image`/`image/<overlay>` positioning marker,
a figure crop) is materialized through the resolver to a **content-addressed** file beside
the record and referenced as `![<derived alt>](<local-file>)`, per §10:

    <!--segment image/figure address: <address>-->   →   ![<derived alt>](<local-file>)

Base rendering follows the same "stored, else derived" decision `corpus body` makes
(§6.2): a record's stored content zone wins when non-empty; a record with no stored
rendering (a fresh stub, a `work`-disposition record awaiting normalize) renders its
**derived** body instead, so an export is never empty just because a record hasn't been
through a normalize pass yet.

**Pass-through segments.** Only the four content atoms carry a rendering; `image` is the
one atom whose body-empty positioning marker (§4.3.2.2) is portably embeddable, so it is
the one that gets materialized. `audio`/`video` segments, a `placement` (§4.3.2.4 — a
member sits here; its own rendering lives on the member's own record, out of scope for a
single-record export per the owner ruling: no bundling), and a whole record governed by a
terminal contract (`form/passthrough` / `form/manifest`, §7.8, `schemas_default/form/
passthrough.yaml`) with nothing else to show all render as an honest, clearly-styled
placeholder naming the address and what it stands for — never silently dropped. See
`PassthroughNote` / `_passthrough_md`.

**Annotated mode** (`annotated=True`) adds: a metadata front block (record id, mime,
origin, hash, touch chain); a `` `[atom @ address]` `` label trailing every rendered
segment; and `corpus.lint` findings rendered as redline callouts immediately after the
segment their address points at (unaddressed findings are listed in a closing section, so
nothing a lint pass found is silently dropped from the annotated view).

Both placeholders and redlines use one shared markup convention — a blockquote whose first
line is `[!KIND] title` — that reads as a plain quote in any markdown viewer and renders as
a colored callout box under Typst (`corpus.typeset._blockquote_to_typst`).
"""

from __future__ import annotations

import json
import logging
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from corpus import derive, records, resolver, segments, typeset
from corpus import functional_uri as furi
from corpus import lint as lint_mod
from corpus.store import ArtifactMissing

log = logging.getLogger(__name__)

DEFAULT_FORMATS: tuple[str, ...] = ("md",)
ALL_FORMATS: tuple[str, ...] = ("md", "typst", "pdf")


# ---------- result shape ---------- #


@dataclass
class MaterializedAsset:
    """One addressed surface, resolved and copied beside the export — named by the
    blake3 of its canonical functional URI (the same hash the resolver cache keys its
    own entries on), so two segments addressing the same surface within one record
    dedup to a single file."""

    address: str
    urihash: str
    filename: str
    path: Path
    alt: str = ""


@dataclass
class PassthroughNote:
    """One place the export declines to reduce content to a textual/visual proxy —
    honest by construction: the reader always gets a named address and a reason,
    never a silent gap."""

    address: str | None
    kind: str  # "record" | "audio" | "video" | "placement" | "unresolved"
    detail: str


@dataclass
class ExportResult:
    record_id: str
    out_dir: Path
    md_path: Path | None = None
    typ_path: Path | None = None
    pdf_path: Path | None = None
    assets: list[MaterializedAsset] = field(default_factory=list)
    passthroughs: list[PassthroughNote] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


# ---------- small address helpers (mirrors corpus._cli.view's, kept local/private) ---------- #


def _addr_list(raw: Any) -> list[str]:
    if isinstance(raw, list):
        return [str(a) for a in raw if a]
    return [str(raw)] if raw else []


def _address_tag(raw: Any) -> str:
    addrs = _addr_list(raw)
    return ", ".join(addrs) if addrs else "the whole transport"


def _address_keys(raw: Any) -> list[str]:
    """A segment's own address string(s), plus the leading axis of any chained address
    (`page=3&bbox=…` also matches a finding scoped to `page=3`) — the same chain-closure
    equivalence `corpus._cli.view._placed_addresses` applies."""
    keys = _addr_list(raw)
    return keys + [k.split("&", 1)[0] for k in keys if "&" in k]


# ---------- base content: stored, else derived (mirrors `corpus body`) ---------- #


def _record_content_text(post: Any, corpus_root: Path) -> tuple[str, str | None]:
    """The record's content-zone text: stored when non-empty, else the derived `body`
    op (spec §6.2) — exactly the decision `corpus body` makes. Returns `(text, warning)`;
    a record with no stored rendering AND no drafter/artifact yields `("", warning)`."""
    stored = post.content or ""
    if stored.strip():
        return stored, None
    from corpus.derive import DeriveError

    try:
        return derive.derive_body(post, corpus_root), None
    except (DeriveError, ArtifactMissing) as exc:
        return "", f"could not derive body: {exc}"


def _terminal_note(post: Any, corpus_root: Path, *, has_content: bool) -> PassthroughNote | None:
    """A whole-record pass-through notice when there is nothing else to render and the
    record's derived state (§4.1) says why: `terminal` (a named terminal contract governs
    it) or `proxy` (nothing has rendered it yet). A `formed`/`rendered` record with
    (unexpectedly) no blocks is left alone — that is a parse/content problem the caller's
    own warnings already surface, not a pass-through."""
    if has_content:
        return None
    try:
        state = records.derived_state(post, corpus_root)
    except Exception:
        return None
    record_id = str(post.metadata.get("id") or "")
    if state == "terminal":
        return PassthroughNote(
            address=None,
            kind="record",
            detail=(
                "this record is governed by a terminal form contract (`form/passthrough` "
                "or `form/manifest`, spec §7.8) — its bytes ARE the terminal representation, "
                "and no textual rendering is authored for them by design. Resolve the "
                f"artifact directly: `corpus resolve 'corpus://{record_id}'`"
            ),
        )
    if state == "proxy":
        return PassthroughNote(
            address=None,
            kind="record",
            detail=(
                "this record carries no stored or derivable rendering yet (state: proxy) — "
                "the artifact stands as its own proxy under the identity contract (spec "
                f"§4.1). Resolve the artifact directly: `corpus resolve 'corpus://{record_id}'`"
            ),
        )
    return None


# ---------- the `members` derivation: per-address alt text (spec §10, §6.2) ---------- #


def _members_alt_map(record_id: str, corpus_root: Path, *, regenerate: bool) -> dict[str, str]:
    """`address -> verbatim alt text`, read from the `members` derivation op (§6.2) — §10
    is explicit that export's alt text comes from here, not from the stored roster (which
    by design carries no descriptors) nor from a segment's own `description`. Best-effort:
    an op failure (no drafter for the type, artifact unreadable) yields an empty map rather
    than failing the export — a missing alt degrades to an empty string, never a crash."""
    try:
        path = resolver.resolve(
            f"corpus://{record_id}?members", corpus_root, regenerate=regenerate
        )
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        log.warning("members op unavailable for alt text on %s: %s", record_id, exc)
        return {}
    out: dict[str, str] = {}
    for m in payload.get("members") or []:
        addr, alt = m.get("address"), m.get("alt")
        if addr and alt:
            out[str(addr)] = str(alt)
    return out


def _materialize_address(
    record_id: str, address: str, corpus_root: Path, out_dir: Path, *, regenerate: bool
) -> tuple[MaterializedAsset | None, str | None]:
    """Resolve `corpus://<record_id>?<address>` and copy it into `out_dir`, named by the
    blake3 of its own canonical functional URI — the same hash the resolver's cache keys
    on (`furi.urihash`), reused rather than re-derived so this naming and the cache's
    naming can never disagree."""
    uri = f"corpus://{record_id}?{address}"
    urihash_value = furi.urihash(furi.canonical(furi.parse(uri)))
    try:
        src = resolver.resolve(uri, corpus_root, regenerate=regenerate)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    filename = f"{urihash_value}{src.suffix or '.bin'}"
    dest = out_dir / filename
    if regenerate or not dest.exists():
        shutil.copyfile(src, dest)
    asset = MaterializedAsset(address=address, urihash=urihash_value, filename=filename, path=dest)
    return asset, None


# ---------- pass-through / redline markup (the shared `[!KIND]` admonition convention) ---------- #

_PASSTHROUGH_TITLE: dict[str, str] = {
    "record": "PASSTHROUGH",
    "audio": "PASSTHROUGH",
    "video": "PASSTHROUGH",
    "placement": "PLACEMENT",
    "unresolved": "UNRESOLVED",
}


def _passthrough_md(note: PassthroughNote) -> str:
    kind = _PASSTHROUGH_TITLE.get(note.kind, "PASSTHROUGH")
    where = note.address or "the whole transport"
    return f"> [!{kind}] {where}\n> {note.detail}\n"


def _finding_md(finding: Any) -> str:
    kind = f"LINT-{str(finding.severity).upper()}"
    where = f" @ `{finding.address}`" if finding.address else ""
    return f"> [!{kind}] {finding.rule_id}{where}\n> {finding.message}\n"


def _segment_label(seg: Any) -> str:
    # `seg.overlay` is already the fully-qualified opener token (`text/equation`,
    # `image/photo`) when present — not a bare suffix — so it stands in for `seg.atom`
    # rather than getting prefixed with it again.
    kind = seg.overlay or seg.atom
    return f"`[{kind} @ {_address_tag(getattr(seg, 'address', None))}]`"


# ---------- the walk: content zone blocks → portable markdown ---------- #


def _render_blocks(
    blocks: list[Any],
    *,
    record_id: str,
    corpus_root: Path,
    out_dir: Path,
    alt_map: dict[str, str],
    regenerate: bool,
    annotated: bool,
    findings_by_key: dict[str, list[Any]],
) -> tuple[str, list[MaterializedAsset], list[PassthroughNote], set[str]]:
    parts: list[str] = []
    assets: dict[str, MaterializedAsset] = {}  # urihash -> asset, dedups repeats in-record
    passthroughs: list[PassthroughNote] = []
    used_keys: set[str] = set()

    def emit_findings(seg: Any) -> None:
        if not annotated:
            return
        for key in _address_keys(getattr(seg, "address", None)):
            hits = findings_by_key.get(key)
            if not hits:
                continue
            used_keys.add(key)
            for finding in hits:
                parts.append(_finding_md(finding))

    def label(seg: Any) -> str:
        return f"{_segment_label(seg)}\n" if annotated else ""

    for block in blocks:
        segs = block.segments if isinstance(block, segments.Section) else [block]
        for seg in segs:
            if not isinstance(seg, segments.Segment):
                continue

            if seg.is_structural:
                level = max(1, min(6, seg.level or 1))
                text = (seg.body or "").strip() or "(unlabeled boundary)"
                parts.append(f"{'#' * level} {text}\n")
                parts.append(label(seg))
                emit_findings(seg)
                continue

            if seg.is_placement:
                addrs = _addr_list(seg.address)
                addr = addrs[0] if addrs else None
                note = PassthroughNote(
                    address=addr,
                    kind="placement",
                    detail=(
                        "a member record sits here (spec §4.3.2.4) — its own rendering "
                        "lives on the member's own record; single-record export does not "
                        "bundle it. Resolve or export it on its own: "
                        f"`corpus resolve 'corpus://{record_id}?{addr}'`" if addr
                        else f"`corpus resolve 'corpus://{record_id}'`"
                    ),
                )
                passthroughs.append(note)
                parts.append(_passthrough_md(note))
                parts.append(label(seg))
                emit_findings(seg)
                continue

            if seg.atom == "image":
                for addr in _addr_list(seg.address):
                    key = furi.urihash(furi.canonical(furi.parse(f"corpus://{record_id}?{addr}")))
                    if key not in assets:
                        asset, err = _materialize_address(
                            record_id, addr, corpus_root, out_dir, regenerate=regenerate
                        )
                        if asset is None:
                            note = PassthroughNote(
                                address=addr, kind="unresolved",
                                detail=f"could not materialize this surface — {err}",
                            )
                            passthroughs.append(note)
                            parts.append(_passthrough_md(note))
                            continue
                        asset.alt = alt_map.get(addr) or (seg.description or "")
                        assets[key] = asset
                    asset = assets.get(key)
                    if asset is not None:
                        parts.append(f"![{asset.alt}]({asset.filename})\n")
                parts.append(label(seg))
                emit_findings(seg)
                continue

            if seg.atom in ("audio", "video"):
                addrs = _addr_list(seg.address)
                addr = addrs[0] if addrs else None
                where = f"?{addr}" if addr else ""
                note = PassthroughNote(
                    address=addr,
                    kind=seg.atom,
                    detail=(
                        f"{seg.atom} content is a body-empty positioning marker (spec "
                        "§4.3.2.2) — the bytes are the faithful rendering, and no portable "
                        "textual or visual proxy is materialized here. Resolve it directly: "
                        f"`corpus resolve 'corpus://{record_id}{where}'`"
                    ),
                )
                passthroughs.append(note)
                parts.append(_passthrough_md(note))
                parts.append(label(seg))
                emit_findings(seg)
                continue

            # A content atom (`text`, or an overlay of it — `text/data-table`,
            # `text/equation`, …). `text/equation`'s guidance wraps LaTeX in `$$…$$`
            # already; a body that skipped the wrapping still gets treated as display
            # math rather than rendered as plain escaped prose.
            body = seg.body or ""
            if seg.overlay == "text/equation" and body.strip() and "$" not in body:
                body = f"$${body.strip()}$$"
            if body.strip():
                parts.append(body.strip() + "\n")
            parts.append(label(seg))
            emit_findings(seg)

    md_body = "\n".join(p for p in parts if p.strip())
    return (md_body + "\n" if md_body else ""), list(assets.values()), passthroughs, used_keys


# ---------- frontmatter + annotated metadata block ---------- #


def _frontmatter(post: Any, corpus_root: Path, record_id: str) -> str:
    try:
        title = records.title_for(post, corpus_root) or record_id[:12]
    except Exception:
        title = record_id[:12]
    data: dict[str, Any] = {"title": title, "record_id": record_id}
    try:
        origin_uri = records.primary_origin_uri(post)
    except Exception:
        origin_uri = ""
    if origin_uri:
        data["source"] = origin_uri
    media_type = records.media_type_for(post)
    if media_type:
        data["mime"] = media_type
    dumped = yaml.safe_dump(data, sort_keys=False, allow_unicode=True).strip()
    return f"---\n{dumped}\n---\n\n"


def _annotated_metadata_md(post: Any, record_id: str) -> str:
    media_type = records.media_type_for(post)
    hashes = records.record_hashes(post)
    touch = post.metadata.get("touch")
    touches = touch if isinstance(touch, list) else ([touch] if touch else [])

    lines = ["## export metadata (annotated)", ""]
    lines.append(f"- **record id:** `{record_id}`")
    if media_type:
        lines.append(f"- **mime:** `{media_type}`")
    for origin in records.iter_origin_blocks(post):
        fields = origin.get("fields") or {}
        uri = fields.get("uri")
        if isinstance(uri, list):
            uri = uri[0] if uri else ""
        label = origin.get("id") or "(unqualified)"
        lines.append(f"- **origin:** {label}" + (f" — {uri}" if uri else ""))
    if hashes:
        lines.append(
            "- **hash:** " + ", ".join(f"`{tag}:{hexval}`" for tag, hexval in hashes.items())
        )
    if touches:
        lines.append("- **touch chain:** " + " -> ".join(f"`{t}`" for t in touches))
    lines.append("")
    return "\n".join(lines)


# ---------- the engine ---------- #


def export_record(
    record_id: str,
    record_path: Path,
    corpus_root: Path,
    *,
    formats: tuple[str, ...] = DEFAULT_FORMATS,
    annotated: bool = False,
    out_dir: Path | None = None,
    regenerate: bool = False,
) -> ExportResult:
    """Render one record to `out_dir` (default `<corpus-root>/export/<record_id>/`).
    Idempotent and untracked (spec §10). Never raises for a record-shape problem —
    degradation is reported on `ExportResult.warnings`, matching the honest-failure
    discipline the resolver / view already follow."""
    post = records.load(record_path)
    out_dir = out_dir or (corpus_root / "export" / record_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    result = ExportResult(record_id=record_id, out_dir=out_dir)

    body_text, warning = _record_content_text(post, corpus_root)
    if warning:
        result.warnings.append(warning)
    try:
        blocks = segments.iter_blocks(body_text) if body_text.strip() else []
    except ValueError as exc:
        result.warnings.append(f"content zone did not parse ({exc}) — rendering as empty")
        blocks = []

    findings_by_key: dict[str, list[Any]] = {}
    all_findings: list[Any] = []
    if annotated:
        try:
            lint_blocks = segments.blocks_for_record(post, corpus_root)
            all_findings = list(lint_mod.lint(post, lint_blocks, corpus_root))
        except Exception as exc:
            result.warnings.append(f"lint pass skipped — {type(exc).__name__}: {exc}")
        for finding in all_findings:
            if finding.address:
                findings_by_key.setdefault(finding.address, []).append(finding)

    alt_map = _members_alt_map(record_id, corpus_root, regenerate=regenerate)
    md_body, assets, passthroughs, used_keys = _render_blocks(
        blocks,
        record_id=record_id,
        corpus_root=corpus_root,
        out_dir=out_dir,
        alt_map=alt_map,
        regenerate=regenerate,
        annotated=annotated,
        findings_by_key=findings_by_key,
    )
    result.assets = assets
    result.passthroughs = passthroughs

    terminal_note = _terminal_note(post, corpus_root, has_content=bool(blocks))
    if terminal_note:
        result.passthroughs.insert(0, terminal_note)
        md_body = _passthrough_md(terminal_note) + ("\n" + md_body if md_body.strip() else "\n")

    sections: list[str] = []
    if annotated:
        sections.append(_annotated_metadata_md(post, record_id))
    sections.append(md_body)
    if annotated:
        leftover = [f for f in all_findings if not f.address or f.address not in used_keys]
        if leftover:
            lines = ["## unaddressed findings", ""]
            for finding in leftover:
                where = f" @ `{finding.address}`" if finding.address else ""
                lines.append(
                    f"- **{finding.rule_id}** ({finding.severity}){where} — {finding.message}"
                )
            sections.append("\n".join(lines) + "\n")

    full_md = _frontmatter(post, corpus_root, record_id) + "\n\n".join(
        s for s in sections if s.strip()
    )
    if not full_md.endswith("\n"):
        full_md += "\n"

    suffix = ".annotated" if annotated else ""
    if "md" in formats:
        md_path = out_dir / f"{record_id}{suffix}.md"
        md_path.write_text(full_md, encoding="utf-8")
        result.md_path = md_path

    if "typst" in formats or "pdf" in formats:
        typ_body = typeset.record_typst(full_md, standalone=True)
        typ_path = out_dir / f"{record_id}{suffix}.typ"
        typ_path.write_text(typ_body, encoding="utf-8")
        result.typ_path = typ_path
        if "pdf" in formats:
            if typeset.typst_available():
                pdf_path = out_dir / f"{record_id}{suffix}.pdf"
                if typeset.compile_pdf(typ_path, pdf_path, root=out_dir):
                    result.pdf_path = pdf_path
                else:
                    result.warnings.append("typst compile failed — see log for detail")
            else:
                result.warnings.append(
                    "typst binary not found on PATH — wrote .typ only, skipped PDF"
                )

    return result
