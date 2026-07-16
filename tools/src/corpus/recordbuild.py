"""Record build / decompose / compile.

The mutation op library plus the decompose↔compile working-dir round trip. The ops
here are the single source of truth for building a record's metadata + content +
annotation zones; the manifest is a shorthand command script over exactly these
ops, so `compile` is just "parse the manifest, run the ops". `decompose` is the
exact inverse — it serializes a record back into that command script plus the
body/description sidecar files.

Reconciliation #1: `embed` ops route to the metadata zone (`records.append_embed_block`)
rather than the content-zone block list. Decompose reads embeds from
`post.metadata["_embeds"]` rather than walking the content `blocks` for embed-typed
entries.

Working-dir layout (`decompose <hash> [dir]` → default `/tmp/<id[:12]>/`):

    manifest.corpus            # the shorthand command script (the build program)
    meta.yaml                  # frontmatter core + artifact + origins + classifies
    bodies/<ord>-<loc>-<slug>.md   # one file per lossless segment body
    desc/<ord>-<loc>-<slug>.txt    # one file per description
    .corpus-decompose.json     # lock {record_id, source, orig_sha256, version}

Manifest grammar (one op per line; `#` comments; `shlex` tokenised):

    record  id=<hex>
    embed   <mime> addr=<a|[a|b…]> transport=<algo:hex> [desc=@desc/..] [k=v ...]
    section addr=<a> [entry="..."] [class=<ns>/<id>] [desc=@desc/..] [k=v ...]
    seg     <atom|atom/overlay> addr=<a> [body=@bodies/..] [desc=@desc/..] [entry=..] [perceptual=..] [k=v ...]
    issue   <id[/subtype]> sev=<s> res=<r> detector=<d> [addr=<a>] [desc=@desc/..] [k=v ...]

`seg` enforces body⟺lossless (spec §4.3.2.2): a `body=` ref is permitted only for
a lossless atom/overlay; `image` / `audio` / `video` and a text overlay declaring
`enables_lossless: false` take `desc=` only.

*(3.1)* `status` is retired from the frontmatter (spec §4.1, §12.19). A legacy `record
id=<hex> status=<s>` line reads parse-tolerantly (the `status=` key is accepted and ignored)
but `write_workdir` never emits one — a record's state is derived, never authored on the
manifest line.
"""

from __future__ import annotations

import json
import re
import shlex
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import frontmatter
import yaml

from corpus import hashing, records, schemas, segments

VERSION = "0.1.0"
LOCK_NAME = ".corpus-decompose.json"
MANIFEST_NAME = "manifest.corpus"
META_NAME = "meta.yaml"

_CORE = (
    "id",
    "title",
    "description",
    "transport",
    "canonical",
    "perceptual",
    "visibility",
    "touch",
)

# Prepended (as comments) to every generated manifest.corpus so the grammar sits
# where the agent edits. `#` lines are skipped by read_workdir.
_MANIFEST_HEADER = [
    "# manifest.corpus — one op per line; `#` comments; shlex-tokenised.",
    "# Grammar:",
    "#   record  id=<hex>",
    "#   embed   <mime> addr=<a|[a|b…]> transport=<algo:hex> [desc=@desc/..] [k=v ...]",
    "#   section [form=<form-id>] [addr=<a>] [entry=\"...\"] [desc=@desc/..] [k=v ...]",
    "#   seg     <atom|atom/overlay> addr=<a> [body=@bodies/..] [desc=@desc/..] [entry=..] [k=v ...]",
    "#   seg     structural addr=<a> level=<int> [entry=\"...\"]   # §4.3.2.3 byte-mark",
    "#   issue   <id[/subtype]> sev=<s> res=<r> detector=<d> [addr=<a>] [desc=@desc/..] [k=v ...]",
    "# addr is one address, or a |-SEPARATED list in brackets: [a|b|…]  — NOT commas",
    "#   (a single address such as bbox=x,y,w,h already contains commas).",
    "# section addr is OMITTED on a whole-record form section (§4.3.2.1).",
    "# record state is derived (spec §4.1), never authored — no `status=` on the record line.",
    "# Spec §4.3: embed lives in the METADATA zone (reconciliation #1 vs the v0.x reference).",
    "# body⟺lossless: `body=` is only valid on a lossless atom/overlay (bare text,",
    "#   text/data-table, text/transcript, …). image/audio/video and non-lossless text",
    "#   overlays (e.g. text/data-table-dynamic) take `desc=` only — run `corpus atoms`.",
    "# Edit body/desc sidecar files; rebuild with `corpus compile <dir>`",
    "#   (run it from the corpus root). Final normalize pass: `corpus compile <dir> --model <id>`.",
]


# ====================================================================== #
# Op library — the compile opcodes
# ====================================================================== #


@dataclass
class Build:
    post: frontmatter.Post
    blocks: list[Any] = field(default_factory=list)  # content-zone Section/Segment
    corpus_root: Path | None = None
    _section: segments.Section | None = None


def begin(meta: dict, corpus_root: Path | None) -> Build:
    """Seed a Build from a decomposed `meta.yaml` mapping."""
    fm = dict(meta.get("frontmatter") or {})
    post = frontmatter.Post("", **fm)
    post.metadata["_artifact"] = meta.get("artifact")
    post.metadata["_origins"] = list(meta.get("origins") or [])
    post.metadata["_classifies"] = list(meta.get("classifies") or [])
    post.metadata["_embeds"] = []  # populated by add_embed (reconciliation #1)
    post.metadata["_contexts"] = []
    return Build(post=post, blocks=[], corpus_root=corpus_root)


def begin_from_post(post: frontmatter.Post, corpus_root: Path | None) -> Build:
    """Seed a Build from an already-loaded record `post` — the draft / redraft path.

    Unlike `begin` (which reconstructs a post from a decomposed `meta.yaml`), this
    wraps the live stub post so a drafter can populate the content zone through the
    same ops and `finish` re-emits it. Byte/provenance + metadata-zone frontmatter
    already on the post are preserved; the embed / issue lists default in place (a
    fresh stub carries none; a re-stubbed record has them cleared)."""
    post.metadata.setdefault("_embeds", [])
    post.metadata.setdefault("_contexts", [])
    return Build(post=post, blocks=[], corpus_root=corpus_root)


def add_embed(
    b: Build,
    *,
    media_type: str,
    address,
    transport: str,
    description: str | None = None,
    extra: dict | None = None,
) -> None:
    """Append a metadata-zone `<!--embed-->` block (reconciliation #1).

    Routes through `records.append_embed_block` so embeds live alongside artifact /
    origin / classify in `post.metadata["_embeds"]`, NOT in the content-zone
    `b.blocks` list.
    """
    ex = dict(extra or {})
    if description is not None:
        ex["description"] = description
    records.append_embed_block(
        b.post,
        media_type=media_type,
        address=address,
        transport=transport,
        fields=ex,
    )
    # Embed is metadata-zone; an embed op does NOT close an open section in the
    # content zone (sections track their own children).


def open_section(
    b: Build,
    *,
    address=None,
    entry: str | None = None,
    form: str | None = None,
    description: str | None = None,
    fields: dict | None = None,
) -> segments.Section:
    sec = segments.Section(
        address=address,
        entry=entry,
        form=form,
        description=description,
        extra=dict(fields or {}),
    )
    b.blocks.append(sec)
    b._section = sec
    return sec


def add_segment(
    b: Build,
    *,
    atom: str,
    overlay: str | None = None,
    address,
    body: str | None = None,
    description: str | None = None,
    entry: str | None = None,
    perceptual: str | None = None,
    level: int | None = None,
    extra: dict | None = None,
) -> segments.Segment:
    structural = atom == segments._STRUCTURAL
    if not structural:
        _check_body_lossless(b.corpus_root, atom, overlay, body)
    seg = segments.Segment(
        atom=atom,
        address=address,
        perceptual=perceptual,
        entry=entry,
        description=description,
        body="" if structural else (body or ""),
        extra=dict(extra or {}),
        overlay=overlay,
        level=level,
    )
    if b._section is not None:
        # A content segment's `entry:` is a top-level-only leaf label; a structural
        # byte-mark's `entry:` (the source's own mark text) rides inside a form span.
        if entry and not structural:
            raise ValueError(
                "in-section segment cannot carry `entry` (the section is the TOC unit)"
            )
        b._section.segments.append(seg)
    else:
        b.blocks.append(seg)
    return seg


def add_structural(
    b: Build,
    *,
    address,
    level: int = 1,
    entry: str | None = None,
    extra: dict | None = None,
) -> segments.Segment:
    """Append a structural byte-mark segment (§4.3.2.3) — the record that the source itself
    declares a boundary at `address`, with a `level` and optional `entry` (the mark's own
    text). Body-empty; takes no atom overlay."""
    return add_segment(
        b,
        atom=segments._STRUCTURAL,
        address=address,
        entry=entry,
        level=level,
        extra=extra,
    )


def add_issue(
    b: Build,
    *,
    id: str,
    subtype: str | None = None,
    severity: str,
    resolution: str,
    detector: str,
    address: str | None = None,
    description: str | None = None,
    fields: dict | None = None,
) -> None:
    f = dict(fields or {})
    if description is not None:
        f["description"] = description
    records.append_issue_block(
        b.post,
        id=id,
        subtype=subtype,
        severity=severity,
        resolution=resolution,
        detector=detector,
        address=address,
        fields=f,
    )


def add_context(
    b: Build,
    *,
    namespace: str,
    id: str,
    subtype: str | None = None,
    address: str | None = None,
    fields: dict | None = None,
) -> None:
    """Append a non-issue context block (reference / note / aside / …). `issue`-namespace
    blocks go through `add_issue` (which carries the severity/resolution shape)."""
    f = dict(fields or {})
    if address:
        f = {"address": address, **f}
    records.append_context_block(b.post, namespace=namespace, id=id, subtype=subtype, fields=f)


def add_blocks(b: Build, blocks: list) -> None:
    """Feed pre-built content-zone blocks (`Section` / `Segment` objects produced by a
    drafter's helpers) through the ops, in order — so drafter output enters the record
    via the SAME validated construction path as `compile` (per-segment body⟺lossless
    enforcement via `add_segment`, section nesting) instead of a parallel
    `segments.emit`. Faithful: every Segment / Section field is replayed, so
    `finish(b)` re-emits byte-identically to `segments.emit(blocks)`."""
    for blk in blocks:
        if isinstance(blk, segments.Section):
            open_section(
                b,
                address=blk.address,
                entry=blk.entry,
                form=blk.form,
                description=blk.description,
                fields=blk.extra,
            )
            for seg in blk.segments:
                add_segment(
                    b,
                    atom=seg.atom,
                    overlay=seg.overlay,
                    address=seg.address,
                    body=seg.body or None,
                    description=seg.description,
                    # A structural mark's `entry:` is valid inside a form span (§4.3.2.3).
                    entry=seg.entry if seg.is_structural else None,
                    perceptual=seg.perceptual,
                    level=seg.level,
                    extra=seg.extra,
                )
            b._section = None  # close the section so a later top-level block isn't nested
        elif isinstance(blk, segments.Segment):
            b._section = None  # ensure top-level placement
            add_segment(
                b,
                atom=blk.atom,
                overlay=blk.overlay,
                address=blk.address,
                body=blk.body or None,
                description=blk.description,
                entry=blk.entry,
                perceptual=blk.perceptual,
                level=blk.level,
                extra=blk.extra,
            )
        else:
            raise ValueError(f"add_blocks: unexpected block type {type(blk).__name__}")


def finish(b: Build) -> frontmatter.Post:
    """Emit the content zone and validate grammar.

    Embeds are NOT emitted here — they live in `b.post.metadata["_embeds"]` and are
    serialized by `records.dump()` as part of the metadata zone.
    """
    b.post.content = segments.emit(b.blocks)
    # Re-parse to surface grammar errors before any write.
    segments.iter_blocks(b.post.content or "")
    return b.post


def _check_body_lossless(
    corpus_root: Path | None, atom: str, overlay: str | None, body: str | None
) -> None:
    if not (body and body.strip()):
        return
    if atom != "text":
        raise ValueError(
            f"`{atom}` segment cannot carry a body — only lossless content has a "
            f"body (spec §4.3.2.2)"
        )
    if overlay and corpus_root is not None:
        ov = schemas.load_atomic_overlay(corpus_root, atom, overlay)
        if isinstance(ov, dict) and ov.get("enables_lossless") is False:
            raise ValueError(
                f"`{overlay}` is non-lossless (enables_lossless: false) and cannot "
                f"carry a body — use a `desc=` instead"
            )


# ====================================================================== #
# Manifest value (de)serialisation
# ====================================================================== #


def _slug(address) -> str:
    a = address[0] if isinstance(address, list) else address
    s = re.sub(r"[^a-z0-9]+", "-", str(a).lower()).strip("-")
    return (s[:30] or "x") + ("-plus" if isinstance(address, list) else "")


def _fmt_addr(address) -> str:
    """List addresses use `|` as separator — addresses themselves use `=`, `&`,
    `,` (bbox), `-` (ranges) but not `|`, so this avoids the comma-collision with
    bbox coordinates. `shlex.quote` handles addresses that contain spaces."""
    if isinstance(address, list):
        raw = "[" + "|".join(str(x) for x in address) + "]"
    else:
        raw = str(address)
    return shlex.quote(raw)


def _parse_addr(raw: str):
    raw = raw.strip()
    if raw.startswith("[") and raw.endswith("]"):
        return [x.strip() for x in raw[1:-1].split("|") if x.strip()]
    return raw


def _fmt_scalar(value) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list):
        # The `_fmt_addr` bracket-pipe convention, extended to generic extras so a
        # list-valued extended field — a form codebook (`speakers:`, `participants:`) —
        # is hand-authorable in a manifest, not just shaper-buildable (the transcript
        # pilot's finding). Entries are scalars; `|` inside an entry is unsupported.
        return shlex.quote("[" + "|".join(str(x) for x in value) + "]")
    return shlex.quote(str(value))


class _MetaDumper(yaml.SafeDumper):
    """SafeDumper that renders a multi-line string as a YAML block literal (`|`) instead
    of a single-quoted scalar. A single-quoted multi-line value (a normalized
    `description`, say) wraps onto continuation lines whose first physical line reads
    like a truncated stump — easy to misread or mis-edit in the decomposed meta.yaml. A
    block literal is unambiguous and quote-free, so it hand-edits and round-trips
    cleanly. PyYAML falls back to a quoted style for a value a literal block can't hold
    (e.g. trailing whitespace), so this never produces invalid YAML."""


def _repr_str_block(dumper: yaml.Dumper, data: str):
    style = "|" if "\n" in data else None
    return dumper.represent_scalar("tag:yaml.org,2002:str", data, style=style)


_MetaDumper.add_representer(str, _repr_str_block)


def _typed(raw: str):
    if re.fullmatch(r"-?\d+", raw):
        return int(raw)
    if raw in ("true", "false"):
        return raw == "true"
    if raw.startswith("[") and raw.endswith("]"):
        # Bracket-pipe list (`[a|b|c]`, `_fmt_scalar`'s emit convention) — element-wise
        # typed so `[1|2]` round-trips as ints and a codebook entry as its string. A
        # literal string value that is itself bracket-wrapped is not representable as a
        # bare extra (same tradeoff `_parse_addr` already makes).
        return [_typed(x.strip()) for x in raw[1:-1].split("|") if x.strip()]
    return raw


def _kv(tokens: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for t in tokens:
        if "=" not in t:
            raise ValueError(f"manifest token is not key=value: {t!r}")
        k, _, v = t.partition("=")
        out[k.strip()] = v
    return out


def _filetext(work: Path, ref: str | None) -> str | None:
    if ref is None:
        return None
    if not ref.startswith("@"):
        raise ValueError(f"file ref must start with @: {ref!r}")
    path = work / ref[1:]
    if not path.is_file():
        raise ValueError(f"manifest references missing file: {ref}")
    return path.read_text(encoding="utf-8").rstrip("\n")


def _rest(kv: dict[str, str], used: set[str]) -> dict:
    return {k: _typed(v) for k, v in kv.items() if k not in used}


# ====================================================================== #
# decompose: record → working dir
# ====================================================================== #


def write_workdir(
    post: frontmatter.Post,
    blocks: list,
    out_dir: Path,
    *,
    source: str,
    orig_sha256: str,
    derived_body: str | None = None,
) -> None:
    """Serialize `post` + content-zone `blocks` into a working dir.

    Reads embeds from `post.metadata["_embeds"]` (metadata zone, reconciliation #1).
    `blocks` is the content-zone Section/Segment list from `segments.iter_blocks`.

    `derived_body` — when set (to the `body` op's touch id), the content zone was DERIVED at
    decompose time (a 3.0 stub has no stored body, §6.2), not read from the record. It is
    recorded in the lock (`body_source: derived`, `body_op`) and flagged in the manifest header
    so a compile from this working dir is understood as an authoring act, never a round-trip of
    stored bytes.
    """
    out = Path(out_dir)
    (out / "bodies").mkdir(parents=True, exist_ok=True)
    (out / "desc").mkdir(parents=True, exist_ok=True)

    meta = {
        "frontmatter": {k: post.metadata[k] for k in _CORE if k in post.metadata},
        "artifact": post.metadata.get("_artifact"),
        "origins": post.metadata.get("_origins") or [],
        "classifies": post.metadata.get("_classifies") or [],
    }
    (out / META_NAME).write_text(
        yaml.dump(meta, Dumper=_MetaDumper, sort_keys=False, allow_unicode=True, width=10**9),
        encoding="utf-8",
    )

    ordn = [0]

    def _next() -> int:
        ordn[0] += 1
        return ordn[0]

    def _body_ref(loc: str, address, text: str) -> str:
        n = _next()
        fn = f"{n:04d}-{loc}-{_slug(address)}.md"
        (out / "bodies" / fn).write_text(text, encoding="utf-8")
        return f"@bodies/{fn}"

    def _desc_ref(loc: str, address, text: str) -> str:
        n = _next()
        fn = f"{n:04d}-{loc}-{_slug(address)}.txt"
        (out / "desc" / fn).write_text(text, encoding="utf-8")
        return f"@desc/{fn}"

    derived_header = (
        [
            f"# BODY DERIVED at decompose time by the `{derived_body}` op (§6.2) — this record",
            "#   stores no rendering. Editing + `corpus compile` here is AUTHORING the record's",
            "#   form, NOT round-tripping stored bytes. The compiled record's touch is yours to set.",
        ]
        if derived_body
        else []
    )
    lines: list[str] = [
        *_MANIFEST_HEADER,
        *derived_header,
        f"record id={post.metadata.get('id', '')}",
        "",
    ]

    # ----- Embeds (metadata zone, reconciliation #1) ----- #
    for emit_i, embed in enumerate(post.metadata.get("_embeds") or [], start=1):
        parts = [
            f"embed {embed.get('media_type', '')}",
            f"addr={_fmt_addr(embed.get('address'))}",
            f"transport={embed.get('transport', '')}",
        ]
        ex = dict(embed.get("fields") or {})
        desc = ex.pop("description", None)
        if desc:
            parts.append(
                "desc=" + _desc_ref(f"emit{emit_i}", embed.get("address"), str(desc))
            )
        for k, v in ex.items():
            parts.append(f"{k}={_fmt_scalar(v)}")
        lines.append(" ".join(parts))

    # ----- Content zone (sections + segments) ----- #
    def _seg_line(seg: segments.Segment, loc: str) -> str:
        opener = seg.overlay or seg.atom
        parts = [f"seg {opener}", f"addr={_fmt_addr(seg.address)}"]
        if seg.level is not None:  # structural byte-mark (§4.3.2.3)
            parts.append(f"level={seg.level}")
        if seg.body and seg.body.strip():
            parts.append("body=" + _body_ref(loc, seg.address, seg.body.rstrip("\n")))
        if seg.description:
            parts.append("desc=" + _desc_ref(loc, seg.address, seg.description))
        if seg.entry:
            parts.append("entry=" + shlex.quote(seg.entry))
        if seg.perceptual:
            parts.append(f"perceptual={seg.perceptual}")
        for k, v in (seg.extra or {}).items():
            parts.append(f"{k}={_fmt_scalar(v)}")
        return " ".join(parts)

    sec_i = seg_i = 0
    for blk in blocks:
        if isinstance(blk, segments.Section):
            sec_i += 1
            parts = ["section"]
            if blk.form:
                parts.append(f"form={blk.form}")
            if blk.address is not None:
                parts.append(f"addr={_fmt_addr(blk.address)}")
            if blk.entry:
                parts.append("entry=" + shlex.quote(blk.entry))
            if blk.description:
                loc = blk.address if blk.address is not None else "record"
                parts.append("desc=" + _desc_ref(f"s{sec_i}", loc, blk.description))
            for k, v in (blk.extra or {}).items():
                parts.append(f"{k}={_fmt_scalar(v)}")
            lines.append("")
            lines.append(" ".join(parts))
            for child in blk.segments:
                lines.append(_seg_line(child, f"s{sec_i}"))
        elif isinstance(blk, segments.Segment):
            seg_i += 1
            lines.append(_seg_line(blk, f"seg{seg_i}"))

    # ----- Context blocks (annotations zone) ----- #
    contexts = post.metadata.get("_contexts") or []
    if contexts:
        lines.append("")
        for n, ctx in enumerate(contexts, 1):
            ns = ctx.get("namespace") or ""
            cid = ctx.get("id", "")
            sub = ctx.get("subtype")
            f_ = dict(ctx.get("fields") or {})
            addr = f_.pop("address", None)
            if ns == "issue":
                # Keep the dedicated `issue <id> sev= res= detector=` manifest line.
                opener = f"{cid}/{sub}" if sub else cid
                sev = f_.pop("severity", "")
                res = f_.pop("resolution", "")
                det = f_.pop("detector", "")
                parts = [
                    f"issue {opener}",
                    f"sev={_fmt_scalar(sev)}",
                    f"res={_fmt_scalar(res)}",
                    f"detector={_fmt_scalar(det)}",
                ]
            else:
                # Generic `context <ns>/<id>[/<sub>] k=v…` line for reference/note/aside/…
                opener = f"{ns}/{cid}/{sub}" if sub else f"{ns}/{cid}"
                parts = [f"context {opener}"]
            if addr:
                parts.append(f"addr={_fmt_addr(addr)}")
            for k, v in f_.items():
                if k == "description":
                    parts.append("desc=" + _desc_ref(f"ctx{n}", addr or "record", str(v)))
                else:
                    parts.append(f"{k}={_fmt_scalar(v)}")
            lines.append(" ".join(parts))

    (out / MANIFEST_NAME).write_text("\n".join(lines) + "\n", encoding="utf-8")
    lock: dict[str, Any] = {
        "record_id": post.metadata.get("id", ""),
        "source": source,
        "orig_sha256": orig_sha256,
        "version": VERSION,
        "body_source": "derived" if derived_body else "stored",
    }
    if derived_body:
        lock["body_op"] = derived_body
    (out / LOCK_NAME).write_text(json.dumps(lock, indent=2), encoding="utf-8")


# ====================================================================== #
# compile: working dir → record
# ====================================================================== #


def read_workdir(in_dir: Path, corpus_root: Path | None) -> frontmatter.Post:
    work = Path(in_dir)
    meta = yaml.safe_load((work / META_NAME).read_text(encoding="utf-8")) or {}
    b = begin(meta, corpus_root)
    meta_id = (meta.get("frontmatter") or {}).get("id")

    seen_record = False
    raw_lines = (work / MANIFEST_NAME).read_text(encoding="utf-8").splitlines()
    for ln, raw in enumerate(raw_lines, 1):
        s = raw.strip()
        if not s or s.startswith("#"):
            continue
        try:
            toks = shlex.split(s)
            verb = toks[0]
            if verb == "record":
                kv = _kv(toks[1:])
                if meta_id and kv.get("id") and kv["id"] != meta_id:
                    raise ValueError("record id disagrees with meta.yaml")
                # `status=` on a legacy manifest line is parse-tolerated and ignored — spec
                # §4.1 retires the field; a record's state is derived, never authored here.
                seen_record = True
                continue
            if not seen_record:
                raise ValueError("first op must be `record`")
            if verb == "embed":
                kv = _kv(toks[2:])
                add_embed(
                    b,
                    media_type=toks[1],
                    address=_parse_addr(kv["addr"]),
                    transport=kv["transport"],
                    description=_filetext(work, kv.get("desc")),
                    extra=_rest(kv, {"addr", "transport", "desc"}),
                )
            elif verb == "section":
                kv = _kv(toks[1:])
                # `form=` is the 3.0 spelling; `class=` reads tolerantly (a decomposed dir
                # produced by a 2.x tool). `addr` is optional (whole-record form section).
                open_section(
                    b,
                    address=(_parse_addr(kv["addr"]) if "addr" in kv else None),
                    entry=kv.get("entry"),
                    form=(kv.get("form") or kv.get("class")),
                    description=_filetext(work, kv.get("desc")),
                    fields=_rest(kv, {"addr", "entry", "form", "class", "desc"}),
                )
            elif verb == "seg":
                opener = toks[1]
                atom, slash, _sub = opener.partition("/")
                overlay = opener if slash else None
                kv = _kv(toks[2:])
                add_segment(
                    b,
                    atom=atom,
                    overlay=overlay,
                    address=_parse_addr(kv["addr"]),
                    body=_filetext(work, kv.get("body")),
                    description=_filetext(work, kv.get("desc")),
                    entry=kv.get("entry"),
                    perceptual=kv.get("perceptual"),
                    level=(int(kv["level"]) if "level" in kv else None),
                    extra=_rest(kv, {"addr", "body", "desc", "entry", "perceptual", "level"}),
                )
            elif verb == "issue":
                opener = toks[1]
                iid, _slash, sub = opener.partition("/")
                kv = _kv(toks[2:])
                extras: dict[str, Any] = {}
                for k, v in kv.items():
                    if k in ("sev", "res", "detector", "addr"):
                        continue
                    if k == "desc":
                        extras["description"] = _filetext(work, v)
                    else:
                        extras[k] = _typed(v)
                add_issue(
                    b,
                    id=iid,
                    subtype=(sub or None),
                    severity=kv["sev"],
                    resolution=kv["res"],
                    detector=kv["detector"],
                    address=(_parse_addr(kv["addr"]) if "addr" in kv else None),
                    description=None,
                    fields=extras,
                )
            elif verb == "context":
                ns, _slash, rest = toks[1].partition("/")
                cid, _slash2, sub = rest.partition("/")
                kv = _kv(toks[2:])
                extras = {}
                for k, v in kv.items():
                    if k == "addr":
                        continue
                    extras[k] = _filetext(work, v) if k == "desc" else _typed(v)
                if "desc" in extras:
                    extras["description"] = extras.pop("desc")
                add_context(
                    b,
                    namespace=ns,
                    id=cid,
                    subtype=(sub or None),
                    address=(_parse_addr(kv["addr"]) if "addr" in kv else None),
                    fields=extras,
                )
            else:
                raise ValueError(f"unknown verb {verb!r}")
        except Exception as e:
            # Annotate per-line failures with the line number and raw line.
            if isinstance(e, KeyError):
                key = e.args[0] if e.args else "?"
                detail = f"missing required field: {key}"
            elif isinstance(e, ValueError):
                detail = str(e)
            else:
                detail = f"{type(e).__name__}: {e}"
            raise ValueError(f"manifest line {ln}: {s!r}\n  {detail}") from e

    if not seen_record:
        raise ValueError("manifest has no `record` op")
    return finish(b)


def sha256_file(path: Path) -> str:
    """`sha256:<hex>` for `path` — streamed in chunks via the shared hasher (no whole-file
    slurp), formatted via the canonical `<algo>:<hex>` helper."""
    return records.format_hash("sha256", hashing.hash_file(path, also=("sha256",))["sha256"])
