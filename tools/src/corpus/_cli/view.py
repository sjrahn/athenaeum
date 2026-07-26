"""Render one record as a single self-contained HTML page — every addressed surface
materialized and inlined.

The stop-gap for having no web front end: when you are working a corpus over ssh and want
to check a record with your own eyes — the original artifact, each embed, the exact crop a
`bbox=` segment addresses, and the transcription that sits beside it — this resolves the
record's whole surface set through the resolver and inlines the results as `data:` URIs, so
the output is ONE file to move and nothing to serve.

It is deliberately a read-only projection: it resolves what the record already declares and
never writes to the record, so it can be pointed at anything, at any state, without risk.
"""

from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
import sys
from pathlib import Path
from typing import Any

from corpus import paths, records, resolver, schemas, segments
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg"}
_TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".html", ".xml", ".yaml", ".yml"}
_INLINE_CAP = 12 * 1024 * 1024  # per-asset ceiling; a bigger surface is linked, not inlined
_PAGE_BUDGET = 64 * 1024 * 1024  # whole-page ceiling; see `_Budget`


class _Budget:
    """The page's aggregate inline ceiling, and the count of what it turned away.

    The per-asset `_INLINE_CAP` says nothing about totals, so a record with many large
    surfaces produced a page too big to open: one 43 MB artifact of full-page scans renders
    57 addressed surfaces and reached ~132 MB. Past the ceiling a surface is reported with its
    resolver path instead of its bytes, and the count of what was withheld is DECLARED on the
    page — a truncated view that looks complete is worse than one that is visibly partial.
    """

    def __init__(self, limit: int) -> None:
        self.limit = limit
        self.spent = 0
        self.withheld = 0

    def take(self, size: int) -> bool:
        """Charge a surface's PAGE cost, not its byte size — base64 inflates by 4/3, so a
        budget spent in source bytes under-reports the file it produces by a third. The number
        the flag names is the number the output approaches."""
        cost = size * 4 // 3
        if self.limit and self.spent + cost > self.limit:
            self.withheld += 1
            return False
        self.spent += cost
        return True


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "-o",
        "--out",
        default=None,
        help="Output HTML path (default: <corpus-root>/export/view-<hash12>.html).",
    )
    parser.add_argument(
        "--regenerate",
        action="store_true",
        help="Bypass the resolver cache when materializing each surface.",
    )
    parser.add_argument(
        "--max-inline",
        type=int,
        default=_PAGE_BUDGET,
        metavar="BYTES",
        help=(
            "Whole-page ceiling on inlined surface bytes (default 64 MiB; 0 = unlimited). "
            "Surfaces past it are reported with their resolver path, and the count is declared."
        ),
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    try:
        record_id, path = paths.resolve_record(root, args.target)
    except Exception as exc:  # tolerant by contract: report, never traceback
        print(f"corpus view: {exc}", file=sys.stderr)
        return 1
    post = records.load(path)
    budget = _Budget(max(0, int(getattr(args, "max_inline", _PAGE_BUDGET) or 0)))
    page = _render(root, record_id, post, regenerate=args.regenerate, budget=budget)
    out = (
        Path(args.out).expanduser()
        if args.out
        else root / "export" / f"view-{record_id[:12]}.html"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(page, encoding="utf-8")
    size = out.stat().st_size
    print(f"{out}  ({size / 1024:.0f} KB)")
    return 0


# ---------- surface materialization ---------- #


def _resolve_surface(
    root: Path, record_id: str, address: Any, *, regenerate: bool
) -> tuple[Path | None, str | None]:
    """Materialize one address → (path, error). A list address takes its first element."""
    if isinstance(address, list):
        address = address[0] if address else None
    if not address:
        return None, None
    uri = f"corpus://{record_id}?{address}"
    try:
        return resolver.resolve(uri, root, regenerate=regenerate), None
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"


def _data_uri(path: Path) -> str | None:
    if path.stat().st_size > _INLINE_CAP:
        return None
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def _surface_html(path: Path, budget: _Budget) -> str:
    """An inlined surface: image as <img>, small text as <pre>, anything else as a note."""
    suffix = path.suffix.lower()
    if suffix in _IMAGE_SUFFIXES:
        size = path.stat().st_size
        if not budget.take(size):
            return _note(
                f"withheld to keep the page openable ({size / 1e6:.1f} MB would exceed the "
                f"page budget) — resolve it directly: {path}"
            )
        uri = _data_uri(path)
        if uri is None:
            return _note(f"image too large to inline ({size / 1e6:.1f} MB) — {path}")
        # No <a href> wrapper: that duplicated the same base64 blob a second time (once in
        # href, once in src), doubling every image's contribution to the page's footprint
        # for a "open in new tab" that a right-click on the <img> already gives you.
        return f'<img src="{uri}" alt="">'
    if suffix in _TEXT_SUFFIXES and path.stat().st_size <= 256 * 1024:
        return f"<pre class=surface>{html.escape(path.read_text(errors='replace'))}</pre>"
    return _note(f"resolved to {path.name} ({path.stat().st_size / 1024:.0f} KB) — not inlined")


# ---------- body rendering ---------- #

_ROW_RE = re.compile(r"^\s*\|.*\|\s*$")
_RULE_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")


def _cells(line: str) -> list[str]:
    """Split a pipe-table row. A `||` pair is an EMPTY cell (the data-table convention), so
    splitting on the delimiter — not on non-empty runs — is what keeps columns aligned."""
    return [c.strip() for c in line.strip().strip("|").split("|")]


def _body_html(body: str) -> str:
    """Render a segment body: pipe tables become real tables, everything else stays verbatim."""
    lines = body.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        if _ROW_RE.match(lines[i]):
            block = []
            while i < len(lines) and _ROW_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            out.append(_table_html(block))
            continue
        run = []
        while i < len(lines) and not _ROW_RE.match(lines[i]):
            run.append(lines[i])
            i += 1
        text = "\n".join(run).strip()
        if text:
            out.append(f"<pre class=surface>{html.escape(text)}</pre>")
    return "\n".join(out) or _note("empty body")


def _table_html(rows: list[str]) -> str:
    body_rows = [r for r in rows if not _RULE_RE.match(r)]
    if not body_rows:
        return ""
    head, rest = body_rows[0], body_rows[1:]
    parts = ["<div class=scroll><table>", "<thead><tr>"]
    parts += [f"<th>{html.escape(c)}</th>" for c in _cells(head)]
    parts.append("</tr></thead><tbody>")
    for row in rest:
        parts.append("<tr>" + "".join(f"<td>{html.escape(c)}</td>" for c in _cells(row)) + "</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


# ---------- page ---------- #


def _note(text: str) -> str:
    return f"<p class=note>{html.escape(text)}</p>"


def _kv(label: str, value: Any) -> str:
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        value = ", ".join(str(v) for v in value)
    return f"<div class=kv><span class=k>{html.escape(label)}</span>" \
           f"<span class=v>{html.escape(str(value))}</span></div>"


def _segment_id(seg: segments.Segment) -> str:
    return str(seg.overlay or seg.atom)


def _render(root: Path, record_id: str, post: Any, *, regenerate: bool, budget: _Budget) -> str:
    media_type = records.media_type_for(post)
    try:
        title = records.title_for(post, root) or "(untitled)"
        description = records.description_for(post, root) or ""
    except Exception:
        title, description = "(untitled)", ""

    parts: list[str] = [
        "<title>", html.escape(f"{title} — {record_id[:12]}"), "</title>",
        _CSS,
        f"<h1>{html.escape(title)}</h1>",
        f"<p class=sub><code>{record_id}</code></p>",
    ]
    if description:
        parts.append(f"<p class=desc>{html.escape(description)}</p>")

    parts.append("<section><h2>identity</h2>")
    parts.append(_kv("media type", media_type))
    parts.append(_kv("transport", post.metadata.get("transport")))
    parts.append(_kv("canonical", post.metadata.get("canonical")))
    touch = post.metadata.get("touch")
    parts.append(_kv("touch", touch if isinstance(touch, str) else (touch or [])[-1:] or ""))
    for origin in records.iter_origin_blocks(post):
        fields = origin.get("fields") or {}
        parts.append(_kv(f"origin {origin.get('id') or ''}", fields.get("uri") or fields))
    parts.append("</section>")

    members = list(records.iter_members(post))
    blocks = segments.iter_blocks(post.content or "")
    placed = _placed_addresses(blocks)

    # The roster IS the content when there is no content zone to place anything in — a
    # container record (`form/manifest`, §7.8). There, render every member, up front.
    if members and not blocks:
        parts.append(f"<section><h2>members ({len(members)}) — the content</h2>")
        for member in members:
            parts.append(_member_html(root, record_id, member, regenerate=regenerate,
                                      budget=budget))
        parts.append("</section>")
        members = []

    if not blocks:
        parts.append("<section><h2>content</h2>" + _note(
            "no stored rendering — this record's body is the `body` derivation op"
        ) + "</section>")
    for block in blocks:
        if isinstance(block, segments.Section):
            overlay = schemas.load_form_overlay(root, block.form) if block.form else None
            label = block.form or "(bare section)"
            parts.append(f"<section><h2>section: {html.escape(label)}"
                         + ("" if overlay or not block.form else
                            " <span class=tag warn>no overlay</span>")
                         + "</h2>")
            for key, value in (block.to_header_dict() or {}).items():
                parts.append(_kv(key, value))
            for seg in block.segments:
                parts.append(_segment_html(root, record_id, seg, regenerate=regenerate,
                                           budget=budget))
            parts.append("</section>")
        else:
            parts.append("<section><h2>segment (formless)</h2>")
            parts.append(_segment_html(root, record_id, block, regenerate=regenerate,
                                       budget=budget))
            parts.append("</section>")

    if members:
        unplaced = [m for m in members if not _is_placed(m, placed)]
        parts.append(f"<section><h2>members ({len(members)})</h2>")
        parts.append(_note(
            f"{len(members) - len(unplaced)} placed in the body above; "
            f"{len(unplaced)} unplaced. A placed member is NOT re-rendered here — the body "
            f"already shows it at the derivation the record chose, which for a covered or "
            f"cropped asset is the faithful one and the whole asset is not."
        ))
        parts.append(_members_table(record_id, members, placed))
        if unplaced:
            parts.append(f"<h2>unplaced members ({len(unplaced)})</h2>")
            parts.append(_note(
                "Declared by the record, placed by no segment. Rendered here because this is "
                "the only surface that shows them — and because an unplaced photo usually "
                "means imagery was missed, not that it is chrome."
            ))
            for member in unplaced:
                parts.append(_member_html(root, record_id, member, regenerate=regenerate,
                                          budget=budget))
        parts.append("</section>")

    if budget.withheld:
        # Declared, not silent: a truncated page that reads as exhaustive is the failure mode
        # this guards against (the same honesty the lint layer applies to capped findings).
        parts.append(
            "<section><h2>withheld</h2>"
            + _note(
                f"{budget.withheld} surface(s) were not inlined — the page reached its "
                f"{budget.limit / 1e6:.0f} MB budget after {budget.spent / 1e6:.0f} MB. "
                f"Raise it with `--max-inline BYTES` (0 = unlimited), or resolve those "
                f"surfaces individually."
            )
            + "</section>"
        )

    contexts = list(records.iter_context_blocks(post))
    if contexts:
        parts.append(f"<section><h2>annotations ({len(contexts)})</h2>")
        for ctx in contexts:
            name = "/".join(x for x in (ctx.get("namespace"), ctx.get("id"),
                                        ctx.get("subtype")) if x)
            parts.append(f"<div class=block><h3>{html.escape(name)}</h3>")
            for key, value in (ctx.get("fields") or {}).items():
                parts.append(_kv(key, value))
            parts.append("</div>")
        parts.append("</section>")
    return "\n".join(parts)


def _addr_list(raw: Any) -> list[str]:
    """A block's address(es) as strings — scalar or list (spec §4.3.1.4)."""
    if isinstance(raw, list):
        return [str(a) for a in raw if a]
    return [str(raw)] if raw else []


def _placed_addresses(blocks: list[Any]) -> set[str]:
    """Every address the content zone places an asset at, plus the leading axis of each chain.

    Deliberately the same semantics as lint's `embed-unreferenced` reference set: SEGMENT
    addresses only — a section's span address is a form span, not a placement — plus the
    chain closure, so a crop at `el=3&cover=…&bbox=…` counts as placing the `el=3` asset. That
    equivalence is the point: what the viewer declines to re-render must be exactly what lint
    considers placed, or the two disagree about the same record.
    """
    placed: set[str] = set()
    for block in blocks:
        children = block.segments if isinstance(block, segments.Section) else [block]
        for seg in children:
            for addr in _addr_list(getattr(seg, "address", None)):
                placed.add(addr)
                if "&" in addr:
                    placed.add(addr.split("&", 1)[0])
    return placed


def _is_placed(member: dict[str, Any], placed: set[str]) -> bool:
    return any(a in placed for a in _addr_list(member.get("address")))


def _members_table(record_id: str, members: list[dict[str, Any]], placed: set[str]) -> str:
    """The roster as metadata — no bytes resolved, no pixels inlined.

    This is the whole shape of the change: the roster is an index (spec §4.3.1.4), so the
    viewer presents it as one. Rendering every member up front meant a page showed each asset
    twice — once raw at the top, once again in the body at the derivation the record actually
    chose — and on a record whose crops cover page chrome, the raw copy was the LESS faithful
    of the two while being the first thing the eye landed on.
    """
    rows = [
        "<div class=scroll><table><thead><tr>"
        "<th>address</th><th>media type</th><th>bytes</th><th>placed</th><th>resolve</th>"
        "</tr></thead><tbody>"
    ]
    for member in members:
        addrs = _addr_list(member.get("address"))
        size = (member.get("fields") or {}).get("bytes")
        where = "placed" if _is_placed(member, placed) else "UNPLACED"
        rows.append(
            "<tr>"
            f"<td>{html.escape(', '.join(addrs))}</td>"
            f"<td>{html.escape(str(member.get('media_type') or ''))}</td>"
            f"<td>{'' if size is None else f'{int(size):,}'}</td>"
            f"<td>{where}</td>"
            f"<td><code>corpus resolve 'corpus://{html.escape(record_id[:12])}…"
            f"?{html.escape(addrs[0] if addrs else '')}'</code></td>"
            "</tr>"
        )
    rows.append("</tbody></table></div>")
    return "".join(rows)


def _member_html(
    root: Path, record_id: str, member: dict[str, Any], *, regenerate: bool, budget: _Budget
) -> str:
    """One member rendered with its bytes — for the two cases that have nowhere else to show:
    a container whose roster IS its content, and an unplaced asset."""
    address = member.get("address")
    out = [
        f"<div class=block><h3>{html.escape(str(address))} "
        f"<span class=tag>{html.escape(str(member.get('media_type') or ''))}</span></h3>"
    ]
    path, err = _resolve_surface(root, record_id, address, regenerate=regenerate)
    out.append(_surface_html(path, budget) if path else _note(err or "no address"))
    out.append("</div>")
    return "\n".join(out)


def _segment_html(
    root: Path, record_id: str, seg: segments.Segment, *, regenerate: bool, budget: _Budget
) -> str:
    if seg.is_structural:
        return (f"<div class=block><h3>structural mark "
                f"<span class=tag>{html.escape(str(seg.address))}</span></h3></div>")
    parts = [f"<div class=block><h3>{html.escape(_segment_id(seg))} "
             f"<span class=tag>{html.escape(str(seg.address))}</span></h3>"]
    for key, value in (seg.extra or {}).items():
        parts.append(_kv(key, value))
    if seg.description:
        parts.append(f"<p class=desc>{html.escape(seg.description)}</p>")
    # EVERY segment's address gets resolved, not just the ones carrying a `bbox=`. A
    # transcription's address is its provenance whatever ops it chains — `cover=` alone, a
    # crop, or a bare axis — and the point of this page is to put that surface next to what
    # was read off it. Resolve FIRST so the eye lands on the source before the reading.
    path, err = _resolve_surface(root, record_id, seg.address, regenerate=regenerate)
    if path:
        parts.append(_surface_html(path, budget))
    elif err:
        # Surfaced loudly either way: a marker that will not resolve is a broken record, and
        # a TRANSCRIPTION whose address will not resolve has lost its provenance — which is
        # exactly the shape of the pixel-vs-fraction `bbox=` drift.
        parts.append(_note(f"address does not resolve — {err}"))
    if seg.body.strip():
        parts.append(_body_html(seg.body))
    parts.append("</div>")
    return "\n".join(parts)


_CSS = """<style>
:root { --fg:#1a1a1a; --bg:#fff; --mut:#666; --line:#dcdcdc; --card:#fafafa; --acc:#0b6bcb; }
@media (prefers-color-scheme: dark) {
  :root { --fg:#e8e8e8; --bg:#141414; --mut:#9a9a9a; --line:#333; --card:#1d1d1d; --acc:#6fb3ff; }
}
:root[data-theme=dark] {
  --fg:#e8e8e8; --bg:#141414; --mut:#9a9a9a; --line:#333; --card:#1d1d1d; --acc:#6fb3ff;
}
:root[data-theme=light] {
  --fg:#1a1a1a; --bg:#fff; --mut:#666; --line:#dcdcdc; --card:#fafafa; --acc:#0b6bcb;
}
body { margin:0 auto; padding:2rem 1.25rem 6rem; max-width:1100px; background:var(--bg);
  color:var(--fg); font:15px/1.55 ui-sans-serif, system-ui, -apple-system, sans-serif; }
h1 { font-size:1.5rem; margin:0 0 .25rem; }
h2 { font-size:.78rem; text-transform:uppercase; letter-spacing:.09em; color:var(--mut);
  margin:2.5rem 0 .75rem; border-bottom:1px solid var(--line); padding-bottom:.35rem; }
h3 { font-size:.95rem; margin:0 0 .5rem; font-family:ui-monospace, SFMono-Regular, monospace; }
.sub { color:var(--mut); margin:0 0 1rem; font-size:.85rem; }
.desc { color:var(--fg); background:var(--card); border-left:3px solid var(--acc);
  padding:.6rem .8rem; margin:.5rem 0; border-radius:0 4px 4px 0; }
.note { color:var(--mut); font-style:italic; margin:.5rem 0; }
.block { border:1px solid var(--line); border-radius:6px; padding:.9rem 1rem; margin:1rem 0; }
.kv { display:flex; gap:.75rem; padding:.15rem 0; font-size:.85rem; }
.k { color:var(--mut); min-width:11rem; flex:0 0 auto; }
.v { word-break:break-word; font-family:ui-monospace, SFMono-Regular, monospace; }
.tag { font-size:.7rem; color:var(--mut); border:1px solid var(--line); border-radius:3px;
  padding:.1rem .35rem; font-weight:400; }
.tag.warn { color:#b45309; border-color:#b45309; }
img { max-width:100%; height:auto; display:block; margin:.75rem 0; background:#fff;
  border:1px solid var(--line); border-radius:4px; }
.scroll { overflow-x:auto; margin:.75rem 0; }
table { border-collapse:collapse; font-size:.85rem; min-width:100%; }
th, td { border:1px solid var(--line); padding:.35rem .55rem; text-align:left;
  vertical-align:top; white-space:nowrap; }
th { background:var(--card); font-weight:600; }
pre.surface { background:var(--card); border:1px solid var(--line); border-radius:4px;
  padding:.7rem .85rem; overflow-x:auto; font-size:.83rem; white-space:pre-wrap; }
code { font-family:ui-monospace, SFMono-Regular, monospace; font-size:.85em; }
</style>"""
