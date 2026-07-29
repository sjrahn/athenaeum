"""Bundle one record for human eyes — `<record-id>.zip` carrying the artifact, the record,
and a self-contained HTML page that shows both.

The stop-gap for having no web front end: when you are working a corpus over ssh and want
to check a record with your own eyes — the original artifact, each member, the exact crop a
`bbox=` segment addresses, and the transcription that sits beside it — this resolves the
record's whole surface set through the resolver and inlines the results as `data:` URIs.

The bundle is three files, named for what they are rather than for their hash, because inside
a container named by the id the id adds nothing:

    <record-id>.zip
      ├── artifact.<ext>   the original captured bytes, verbatim
      ├── record.md        the record file, verbatim
      └── index.html       the page: reading view + record source, cross-linked

`index.html` stays **self-contained** — every surface inlined, exactly as before — so it still
works pulled out of the bundle on its own; the sibling files are an addition, not a dependency.
It carries two views of one record: the **reading view** (the record's own rendering, each
address resolved and materialized beside what was read off it) and the **record source** (the
`.md` verbatim, line-numbered, with every address a link into the reading view). The pairing is
the point — the friendly view is a projection, and the projection is easy to trust too far, so
the bytes that produced it sit one click away in the same file.

It is deliberately a read-only projection: it resolves what the record already declares and
never writes to the record, so it can be pointed at anything, at any state, without risk.
"""

from __future__ import annotations

import argparse
import base64
import html
import mimetypes
import re
import shutil
import sys
import zipfile
from pathlib import Path
from typing import Any

from corpus import assembly, containment, paths, records, resolver, schemas, segments
from corpus import mime as mime_mod
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

_IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".avif", ".svg"}
_TEXT_SUFFIXES = {".txt", ".md", ".json", ".csv", ".html", ".xml", ".yaml", ".yml"}
_INLINE_CAP = 12 * 1024 * 1024  # per-asset ceiling; a bigger surface is linked, not inlined
_PAGE_BUDGET = 64 * 1024 * 1024  # whole-page ceiling; see `_Budget`

_RECORD_MEMBER = "record.md"
_PAGE_MEMBER = "index.html"

# Bundle members are pinned to a fixed DOS timestamp so rebuilding the same record's bundle
# produces the same bytes. Nothing here is content-addressed by its own hash — the name comes
# from the RECORD's id — but a viewer that wobbles with filesystem mtimes invites "why did my
# bundle change" for no gain, and reproducibility is free at this size.
_BUNDLE_EPOCH = (1980, 1, 1, 0, 0, 0)
_CREATE_SYSTEM_UNIX = 3  # pinned like `assembly.write_bundle`: bytes must not depend on the OS

# DEFLATE, deliberately — not the zstd routing `assembly.write_bundle` uses. That writer serves
# archival bundles whose reader is the corpus itself; this bundle's reader is a person's unzip,
# Finder, or Explorer, none of which open a zstd-compressed zip. Universal readability IS the
# requirement here, so the compression choice differs from the archival path on purpose.
_BUNDLE_COMPRESSION = zipfile.ZIP_DEFLATED

# The artifact's own ceiling, separate from the page's. Without it the bundle is the one part of
# this command with no bound at all: a 97 MB zip container yields a 95 MB bundle and the 2.1 GB
# mailbox tar yields nothing openable. Past the ceiling the artifact is LEFT OUT and said so —
# the page keeps working (its surfaces are inlined and its record is verbatim), and the honest
# failure is a missing member you were told about, not a bundle nobody can open.
_ARTIFACT_BUDGET = 256 * 1024 * 1024

# *(3.8)* How many placed members' pages ride in a bundle before it stops. A record placing
# 214 members would otherwise produce 214 pages, each re-inlining its own pixels. Past the
# cap the placement still names its member and prints the recovery line; the omission is
# declared on stderr, never silent.
_MEMBER_PAGE_CAP = 25

_CHUNK = 1024 * 1024  # artifact streaming chunk
_ZIP64_LIMIT = (1 << 32) - 1  # forced per-member from the known size, never guessed


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
        help=(
            "Output path (default: <corpus-root>/export/<record-id>.zip, "
            "or view-<hash12>.html under --html)."
        ),
    )
    parser.add_argument(
        "--html",
        action="store_true",
        help=(
            "Write the page alone instead of the bundle — no artifact, no record.md. "
            "The page is self-contained either way; this just skips the zip."
        ),
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
    parser.add_argument(
        "--max-members",
        type=int,
        default=_MEMBER_PAGE_CAP,
        metavar="N",
        help=(
            "How many placed members' records + pages ride in the bundle under members/ "
            f"(default {_MEMBER_PAGE_CAP}; 0 = unlimited). Past it a placement names its "
            "member and prints the recovery line instead of linking."
        ),
    )
    parser.add_argument(
        "--max-artifact",
        type=int,
        default=_ARTIFACT_BUDGET,
        metavar="BYTES",
        help=(
            "Ceiling on the bundled artifact (default 256 MiB; 0 = unlimited). A bigger "
            "artifact is left out of the bundle and the omission is declared on the page."
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
    # `--html` forces the page. Otherwise an explicit `--out` decides by suffix, because
    # `-o page.html` writing a zip named `page.html` is a lie the filesystem then repeats to
    # every tool downstream. Absent both, the bundle is the default.
    bundle = not getattr(args, "html", False)
    if bundle and args.out:
        suffix = Path(args.out).suffix.lower()
        if suffix in (".html", ".htm"):
            bundle = False

    # The artifact is located BEFORE rendering, because the page states what it found: a
    # bundle whose artifact could not be materialized says so on its face rather than
    # shipping a page that links a member which isn't there.
    artifact = (
        _artifact_source(
            root,
            record_id,
            post,
            limit=max(0, int(getattr(args, "max_artifact", _ARTIFACT_BUDGET) or 0)),
        )
        if bundle
        else None
    )

    # *(3.8)* The members this record PLACES (§4.3.2.4). In a bundle each one's own page and
    # record ride alongside under `members/`, and the placement links to it — because a
    # placement's whole meaning is "the reading lives over there," and a viewer that names the
    # destination without going there makes the reader do the resolver's job by hand. In
    # `--html` mode there are no sibling files, so the placement names the member and prints
    # the recovery line instead: a link that goes nowhere would be worse than none.
    leaves = placed_members(root, post)
    cap = max(0, int(getattr(args, "max_members", _MEMBER_PAGE_CAP) or 0))
    bundled: list[_PlacedMember] = []
    if bundle:
        for member in leaves.values():
            if member.record is None or any(b.hex == member.hex for b in bundled):
                continue
            if cap and len(bundled) >= cap:
                break
            # A member gets a DIRECTORY named by its hash, holding the same three names the
            # bundle root holds. Two reasons, and the second is the one that bit: inside a
            # container named by the id, plain names are what belong (the rule the root already
            # follows, applied one level down) — and the member's page emits `href="record.md"`
            # and `href="artifact.<ext>"` relative to itself, so a flat `members/<hash>.html`
            # pointed both at `members/record.md` and `members/artifact.png`, neither of which
            # existed. The directory makes the page's own links true rather than special-casing
            # them.
            member.href = f"members/{member.hex}/{_PAGE_MEMBER}"
            bundled.append(member)
        # A member placed at several addresses shares one page.
        for member in leaves.values():
            match = next((b for b in bundled if b.hex == member.hex), None)
            if match is not None:
                member.href = match.href

    page = _render(
        root,
        record_id,
        post,
        regenerate=args.regenerate,
        budget=budget,
        source=path.read_text(encoding="utf-8", errors="replace") if bundle else None,
        artifact=artifact,
        leaves=leaves,
    )

    if not bundle:
        out = (
            Path(args.out).expanduser()
            if args.out
            else root / "export" / f"view-{record_id[:12]}.html"
        )
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(page, encoding="utf-8")
        print(f"{out}  ({out.stat().st_size / 1024:.0f} KB)")
        return 0

    # Each placed member's own page, rendered exactly as `corpus view` would render it
    # standalone — depth one: a member's own placements name their members but do not recurse,
    # or a container would bundle the corpus.
    extra: list[tuple[str, bytes | None, Path | None]] = []
    for member in bundled:
        assert member.record is not None and member.href is not None
        member_post = records.load(member.record)
        # The member's own bytes ride with it — materialized through containment like any
        # other artifact (§12.9), which for a promoted member means streaming them out of
        # this very record's transport. Without them the member's folder is a page and a
        # record talking about bytes that are not there, and its own artifact link is dead.
        member_artifact = _artifact_source(
            root,
            member.hex,
            member_post,
            limit=max(0, int(getattr(args, "max_artifact", _ARTIFACT_BUDGET) or 0)),
        )
        member_page = _render(
            root,
            member.hex,
            member_post,
            regenerate=args.regenerate,
            budget=_Budget(budget.limit),
            source=member.record.read_text(encoding="utf-8", errors="replace"),
            artifact=member_artifact,
            leaves=placed_members(root, member_post),
        )
        folder = f"members/{member.hex}"
        extra.append((f"{folder}/{_PAGE_MEMBER}", member_page.encode("utf-8"), None))
        extra.append((f"{folder}/{_RECORD_MEMBER}", None, member.record))
        if member_artifact.path:
            extra.append((f"{folder}/{member_artifact.name}", None, member_artifact.path))

    out = Path(args.out).expanduser() if args.out else root / "export" / f"{record_id}.zip"
    size = _write_bundle(out, page=page, record=path, artifact=artifact, extra=extra)
    members = [_PAGE_MEMBER, _RECORD_MEMBER] + ([artifact.name] if artifact and artifact.path
                                                else [])
    print(f"{out}  ({size / 1024:.0f} KB)")
    print(f"  {', '.join(sorted(members))}")
    if bundled:
        print(f"  members/ — {len(bundled)} placed member record(s) + page(s)")
    withheld = sum(1 for m in leaves.values() if m.record is not None and not m.href)
    if withheld:
        # Declared, never silent — same discipline as every other ceiling here.
        print(f"  {withheld} placed member(s) NOT bundled (--max-members {cap})", file=sys.stderr)
    if artifact and not artifact.path:
        # Declared, never silent — same discipline as the page budget: a bundle missing its
        # artifact must be visibly incomplete, on stdout and on the page.
        print(f"  artifact NOT bundled — {artifact.note}", file=sys.stderr)
    return 0


# ---------- the bundle ---------- #


class _Artifact:
    """Where the record's own bytes are, and what to call them in the bundle.

    `path` is None when the bytes are unreachable by any route, and `note` says why — the
    "durable artifact-byte storage unconfirmed" case, or a promoted record whose container is
    gone. The bundle is still written; it is just visibly one member short.
    """

    def __init__(self, name: str, path: Path | None, note: str = "") -> None:
        self.name = name
        self.path = path
        self.note = note

    @property
    def size(self) -> int:
        return self.path.stat().st_size if self.path else 0


def _artifact_source(root: Path, record_id: str, post: Any, *, limit: int) -> _Artifact:
    """Locate the record's artifact bytes, containment-aware, and apply the size ceiling.

    A standalone file in `artifacts/<shard>/` wins and lends its own extension — ingest chose
    that name, so it beats re-deriving one from the media type. Otherwise the bytes are
    materialized the way every derivation reaches them: `containment.ensure_local_bytes`,
    which streams a promoted record's bytes out of its container (spec §2, §12.9).
    """
    media_type = records.media_type_for(post) or "application/octet-stream"
    ext = mime_mod.extension_for(media_type)
    found: Path | None = None

    shard_dir = root / "artifacts" / paths.shard(record_id)
    if shard_dir.is_dir():
        for candidate in sorted(shard_dir.iterdir()):
            if candidate.is_file() and candidate.name.split(".", 1)[0] == record_id:
                ext = candidate.name.split(".", 1)[1] if "." in candidate.name else ext
                found = candidate
                break

    if found is None:
        try:
            found = containment.ensure_local_bytes(root, record_id, ext)
        except Exception as exc:
            return _Artifact(f"artifact.{ext}", None, f"{type(exc).__name__}: {exc}")

    name = f"artifact.{ext}"
    size = found.stat().st_size
    if limit and size > limit:
        return _Artifact(
            name,
            None,
            f"{size / 1e6:.0f} MB exceeds the {limit / 1e6:.0f} MB artifact ceiling "
            f"(raise it with --max-artifact BYTES, 0 = unlimited); the bytes are at {found}",
        )
    return _Artifact(name, found)


def _write_bundle(
    out: Path,
    *,
    page: str,
    record: Path,
    artifact: _Artifact | None,
    extra: list[tuple[str, bytes | None, Path | None]] | None = None,
) -> int:
    """Write the bundle deterministically, atomically, and without holding the artifact.

    Atomic for the same reason `paths.atomic_write_text` is: a bundle is something you hand to
    someone, and a truncated zip that exists is worse than one that doesn't. The artifact is
    STREAMED rather than read whole — the ceiling admits members up to 256 MB by default, and
    a viewer has no business allocating that.
    """
    out.parent.mkdir(parents=True, exist_ok=True)
    partial = out.with_name(out.name + ".partial")
    # (name, inline-bytes-or-None, path-or-None) — sorted, because member order is not an input.
    members: list[tuple[str, bytes | None, Path | None]] = [
        (_PAGE_MEMBER, page.encode("utf-8"), None),
        (_RECORD_MEMBER, None, record),
    ]
    if artifact and artifact.path:
        members.append((artifact.name, None, artifact.path))
    members.extend(extra or [])
    try:
        with zipfile.ZipFile(partial, "w", compression=_BUNDLE_COMPRESSION, allowZip64=True) as zf:
            for name, payload, src in sorted(members, key=lambda m: m[0]):
                info = zipfile.ZipInfo(name, date_time=_BUNDLE_EPOCH)
                # Already-compressed bytes are STORED, reusing assembly's extension table so the
                # two writers agree on what compresses. Deflating a zip/jpg/mp4 artifact burns a
                # pass over every byte to save ~2%: on a 97 MB container that is the whole cost
                # of the command. `index.html` (base64) and `record.md` deflate well.
                info.compress_type = (
                    zipfile.ZIP_STORED if assembly.is_stored_name(name) else _BUNDLE_COMPRESSION
                )
                info.create_system = _CREATE_SYSTEM_UNIX
                info.external_attr = 0o644 << 16
                if payload is not None:
                    zf.writestr(info, payload)
                    continue
                assert src is not None
                size = src.stat().st_size
                info.file_size = size
                with src.open("rb") as fh, zf.open(
                    info, "w", force_zip64=size >= _ZIP64_LIMIT
                ) as dst:
                    shutil.copyfileobj(fh, dst, _CHUNK)
        partial.replace(out)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    return out.stat().st_size


# ---------- surface materialization ---------- #


def _address_tag(address: object) -> str:
    """*(3.8)* How an address reads on the page. An ABSENT one is the whole transport
    (§4.3.2.2) and must say so — `None` is a Python value leaking into a reading view, and it
    reads as a bug rather than as the statement the omission actually is."""
    if address is None or address == []:
        return "the whole transport"
    return str(address)


def _resolve_surface(
    root: Path, record_id: str, address: Any, *, regenerate: bool
) -> tuple[Path | None, str | None]:
    """Materialize one address → (path, error). A list address takes its first element.

    *(3.8)* An **absent** address is not "nothing to resolve" — it names the whole transport
    (§4.3.2.2), and the functional URI for that is the bare `corpus://<id>` the record-side
    omission mirrors. Returning early here was why a promoted member's page showed its
    transcription with no artifact beside it: the one surface the page exists to put there was
    the only one it declined to ask for.
    """
    if isinstance(address, list):
        address = address[0] if address else None
    uri = f"corpus://{record_id}?{address}" if address else f"corpus://{record_id}"
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


# ---------- segment bodies: two lossless shapes, both rendered ---------- #

#: Tags a segment body may contribute to the page. Everything here is structure or emphasis
#: that a faithful table/prose rendering genuinely carries; everything NOT here is unwrapped to
#: its text. The list is a whitelist rather than a blacklist on purpose: a record body is
#: CAPTURED CONTENT, so the viewer must assume it contains anything the open web does. `lint`'s
#: `_HTML_RESIDUE_RE` already objects to `script`/`style`/`iframe` in a body, but a viewer that
#: relied on the corpus being clean would be trusting a gate to hold for a page it hands to a
#: person.
_SAFE_TAGS = frozenset(
    {
        "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption", "colgroup", "col",
        "b", "strong", "i", "em", "u", "s", "sub", "sup", "br", "code", "span", "a",
        "p", "ul", "ol", "li", "h1", "h2", "h3", "h4", "h5", "h6", "blockquote", "hr", "pre",
    }
)
#: Per-tag attribute whitelist. `rowspan`/`colspan` are load-bearing — a fuse table's merged
#: header cells are part of what the transcription says — and dropping them would silently
#: reshape the data the record attests.
_SAFE_ATTRS = {
    "th": ("rowspan", "colspan", "scope"),
    "td": ("rowspan", "colspan"),
    "col": ("span",),
    "colgroup": ("span",),
    "a": ("href", "title"),
}
_SAFE_SCHEMES = ("http://", "https://", "mailto:", "#")
#: Dropped WITH their contents rather than unwrapped: their text is not content.
_DROP_ENTIRELY = frozenset({"script", "style", "iframe", "object", "embed", "template"})


def _sanitize_html(fragment: str) -> str:
    """A captured HTML fragment, reduced to the whitelist above and re-serialized."""
    from bs4 import BeautifulSoup, Tag

    soup = BeautifulSoup(fragment, "html.parser")
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag):
            continue
        if tag.name in _DROP_ENTIRELY:
            tag.decompose()
            continue
        if tag.name not in _SAFE_TAGS:
            tag.unwrap()  # keep the text, drop the element
            continue
        allowed = _SAFE_ATTRS.get(tag.name, ())
        for attr in list(tag.attrs):
            if attr not in allowed:
                del tag[attr]
        href = tag.get("href")
        if isinstance(href, str) and not href.lower().startswith(_SAFE_SCHEMES):
            del tag["href"]
    return str(soup)


_HTML_BODY_RE = re.compile(r"^\s*<(table|ul|ol|dl|p|h[1-6])\b", re.IGNORECASE)
_MD_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*)$")
_MD_BULLET_RE = re.compile(r"^\s*[-*+]\s+(.*)$")
_MD_ORDERED_RE = re.compile(r"^\s*\d+[.)]\s+(.*)$")


def _inline_md(text: str) -> str:
    """Markdown emphasis, code, and links inside one line of already-ESCAPED text.

    Escaping first and matching after is deliberate: the delimiters (`*`, backtick, brackets)
    survive escaping unchanged, so the order costs nothing and means no body can inject markup
    by writing it out longhand.
    """
    out = html.escape(text)
    out = re.sub(r"`([^`]+)`", r"<code>\1</code>", out)
    out = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", out)
    out = re.sub(r"(?<![\w*])\*([^*\n]+)\*(?![\w*])", r"<em>\1</em>", out)
    out = re.sub(
        r"\[([^\]]+)\]\((https?://[^\s)]+|#[^\s)]*)\)",
        r'<a href="\2">\1</a>',
        out,
    )
    return out


def _body_html(body: str) -> str:
    """Render a segment body as what it IS.

    Two lossless shapes reach here and both used to land in a `<pre>`: a `text/data-table`
    whose transcription is a literal HTML `<table>` (the drafter's shape for a table it read
    out of HTML), and markdown (the normalizer's shape). Showing either as source made the
    reader parse a table by eye, which is the one job the page exists to do for them — and it
    is the projection this command is *for*. The record itself is untouched either way; this is
    a read-time rendering of the body's own bytes.
    """
    if _HTML_BODY_RE.match(body):
        return f"<div class=scroll>{_sanitize_html(body)}</div>"

    lines = body.splitlines()
    out: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i]
        if _ROW_RE.match(line):
            block = []
            while i < len(lines) and _ROW_RE.match(lines[i]):
                block.append(lines[i])
                i += 1
            out.append(_table_html(block))
            continue
        heading = _MD_HEADING_RE.match(line)
        if heading:
            level = min(6, len(heading.group(1)) + 2)  # never outranks the page's own h2/h3
            out.append(f"<h{level}>{_inline_md(heading.group(2))}</h{level}>")
            i += 1
            continue
        if _MD_BULLET_RE.match(line) or _MD_ORDERED_RE.match(line):
            ordered = bool(_MD_ORDERED_RE.match(line))
            items: list[str] = []
            while i < len(lines):
                m = _MD_ORDERED_RE.match(lines[i]) if ordered else _MD_BULLET_RE.match(lines[i])
                if not m:
                    break
                items.append(f"<li>{_inline_md(m.group(1))}</li>")
                i += 1
            tag = "ol" if ordered else "ul"
            out.append(f"<{tag}>{''.join(items)}</{tag}>")
            continue
        if not line.strip():
            i += 1
            continue
        para: list[str] = []
        while i < len(lines) and lines[i].strip():
            nxt = lines[i]
            if _ROW_RE.match(nxt) or _MD_HEADING_RE.match(nxt) or _MD_BULLET_RE.match(nxt):
                break
            para.append(nxt)
            i += 1
        if para:
            out.append("<p>" + "<br>".join(_inline_md(p) for p in para) + "</p>")
    return "\n".join(out) or _note("empty body")


def _table_html(rows: list[str]) -> str:
    body_rows = [r for r in rows if not _RULE_RE.match(r)]
    if not body_rows:
        return ""
    head, rest = body_rows[0], body_rows[1:]
    parts = ["<div class=scroll><table>", "<thead><tr>"]
    # Cells carry markdown too — a fuse table's `**Primary Fuses**` section row is emphasis,
    # not literal asterisks, and escaping alone showed the source where the reading belongs.
    parts += [f"<th>{_inline_md(c)}</th>" for c in _cells(head)]
    parts.append("</tr></thead><tbody>")
    for row in rest:
        parts.append("<tr>" + "".join(f"<td>{_inline_md(c)}</td>" for c in _cells(row)) + "</tr>")
    parts.append("</tbody></table></div>")
    return "".join(parts)


# ---------- the record source view ---------- #

_ANCHOR_UNSAFE = re.compile(r"[^A-Za-z0-9]+")


def _anchor_targets(addrs: list[str], claimed: set[str]) -> tuple[str, str]:
    """`(id_attr, alias_spans)` for a rendered block, given the ids already handed out.

    An element carries one id, but a block may answer to several addresses — a list address is
    one asset at several positions, and the source view links every occurrence. The extras
    become empty `<span id=…>` jump targets inside the block, so no declared address links
    nowhere.

    `claimed` makes the ids unique even on a record that shouldn't exist: two segments sharing
    an address is a lint violation (`segment-address-duplicate`), but this viewer is pointed at
    records in any state, and emitting a duplicate id would silently send both links to the
    first one.
    """
    ids: list[str] = []
    for addr in addrs:
        anchor = _anchor(addr)
        if anchor not in claimed:
            claimed.add(anchor)
            ids.append(anchor)
    if not ids:
        return "", ""
    aliases = "".join(f'<span class=alias id="{a}"></span>' for a in ids[1:])
    return f' id="{ids[0]}"', aliases


def _anchor(address: str) -> str:
    """A stable DOM id for an address. Pure, so the reading view and the source view derive the
    same id independently — no id map has to be threaded between them."""
    return "at-" + _ANCHOR_UNSAFE.sub("-", str(address)).strip("-").lower()


def _known_addresses(blocks: list[Any], members: list[dict[str, Any]]) -> list[str]:
    """Every address that has a rendered target in the reading view — segments and member rows.

    A section's own span address is deliberately excluded: it is a form span, not a placement,
    and it materializes no surface. Same distinction `_placed_addresses` draws, kept identical
    on purpose — the two must not disagree about what an address means.
    """
    found: list[str] = []
    for block in blocks:
        children = block.segments if isinstance(block, segments.Section) else [block]
        for seg in children:
            found += _addr_list(getattr(seg, "address", None))
    for member in members:
        found += _addr_list(member.get("address"))
    return sorted(set(found))


def _source_html(source: str, known: list[str]) -> str:
    """The record verbatim, line-numbered, with each address a link into the reading view.

    Escaped FIRST, then marked up — the record is full of `<!--` block openers, so any other
    order would either double-escape the markup we insert or emit the record's own angle
    brackets as live HTML.

    Address linking is ONE regex pass over an alternation sorted longest-first. Two passes would
    corrupt the output: after `el=3&bbox=0,0,1,1` became an anchor, a second pass for `el=3`
    would match inside that anchor's own link text.
    """
    escaped_to_anchor = {html.escape(a): _anchor(a) for a in known}
    pattern = (
        re.compile("|".join(re.escape(e) for e in sorted(escaped_to_anchor, key=len, reverse=True)))
        if escaped_to_anchor
        else None
    )

    def link(match: re.Match[str]) -> str:
        text = match.group(0)
        return f'<a class=addr href="#{escaped_to_anchor[text]}">{text}</a>'

    out: list[str] = ['<pre class=src>']
    for number, line in enumerate(source.splitlines(), 1):
        body = html.escape(line)
        if pattern is not None:
            body = pattern.sub(link, body)
        stripped = line.strip()
        cls = "ln"
        if stripped.startswith("<!--") or stripped == "-->" or stripped == "---":
            cls += " cm"
        # No newline between spans: `.ln` is display:block, so a literal newline inside the
        # <pre> would render a second blank line for every line of the record.
        out.append(f'<span class="{cls}" data-n="{number}">{body or " "}</span>')
    out.append("</pre>")
    return "".join(out)


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


def _render(
    root: Path,
    record_id: str,
    post: Any,
    *,
    regenerate: bool,
    budget: _Budget,
    source: str | None = None,
    artifact: _Artifact | None = None,
    leaves: dict[str, _PlacedMember] | None = None,
) -> str:
    media_type = records.media_type_for(post)
    try:
        title = records.title_for(post, root) or "(untitled)"
        description = records.description_for(post, root) or ""
    except Exception:
        title, description = "(untitled)", ""

    parts: list[str] = [
        # Doctype + charset, declared rather than inferred. The page is UTF-8 throughout (record
        # titles are full of em-dashes, °, µ) and it is now opened from a `file://` path after
        # someone unzips the bundle — where a browser with no declared encoding falls back to a
        # locale default and renders mojibake. Standards mode also keeps the CSS predictable.
        "<!doctype html>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        "<title>", html.escape(f"{title} — {record_id[:12]}"), "</title>",
        _CSS,
        f"<h1>{html.escape(title)}</h1>",
        f"<p class=sub><code>{record_id}</code></p>",
    ]
    if description:
        parts.append(f"<p class=desc>{html.escape(description)}</p>")

    if source is not None:
        parts.append(_tabs_html(artifact))
    parts.append("<div id=view-read>")

    parts.append("<section><h2>identity</h2>")
    parts.append(_kv("media type", media_type))
    parts.append(_kv("transport", post.metadata.get("transport")))
    parts.append(_kv("canonical", post.metadata.get("canonical")))
    touch = post.metadata.get("touch")
    parts.append(_kv("touch", touch if isinstance(touch, str) else (touch or [])[-1:] or ""))
    for origin in records.iter_origin_blocks(post):
        fields = origin.get("fields") or {}
        parts.append(_kv(f"origin {origin.get('id') or ''}", fields.get("uri") or fields))
    if artifact is not None:
        if artifact.path:
            parts.append(
                f"<div class=kv><span class=k>artifact</span><span class=v>"
                f'<a href="{html.escape(artifact.name)}" download>{html.escape(artifact.name)}</a>'
                f" &middot; {artifact.size:,} bytes</span></div>"
            )
        else:
            parts.append(_kv("artifact", f"NOT bundled — {artifact.note}"))
    parts.append("</section>")

    claimed: set[str] = set()  # DOM ids handed out, so no address gets two targets
    members = list(records.iter_members(post))
    blocks = segments.iter_blocks(post.content or "")
    placed = _placed_addresses(blocks)

    # The roster IS the content when there is no content zone to place anything in — a
    # container record (`form/manifest`, §7.8). There, render every member, up front.
    if members and not blocks:
        parts.append(f"<section><h2>members ({len(members)}) — the content</h2>")
        for member in members:
            parts.append(_member_html(root, record_id, member, regenerate=regenerate,
                                      budget=budget, claimed=claimed))
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
                                           budget=budget, claimed=claimed, leaves=leaves))
            parts.append("</section>")
        else:
            parts.append("<section><h2>segment (formless)</h2>")
            parts.append(_segment_html(root, record_id, block, regenerate=regenerate,
                                       budget=budget, claimed=claimed, leaves=leaves))
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
                                          budget=budget, claimed=claimed))
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

    parts.append("</div>")  # /view-read

    if source is not None:
        all_members = list(records.iter_members(post))
        parts.append("<div id=view-src>")
        parts.append(f"<section><h2>record source &mdash; {html.escape(_RECORD_MEMBER)}</h2>")
        parts.append(_note(
            "The record file verbatim. Every address is a link to where the reading view "
            "materialized it — which is the one cross-check the friendly view cannot give you "
            "about itself."
        ))
        parts.append(_source_html(source, _known_addresses(blocks, all_members)))
        parts.append("</section></div>")
        parts.append(_TABS_JS)
    return "\n".join(parts)


def _tabs_html(artifact: _Artifact | None) -> str:
    """View switch + the sibling-file links.

    Without JS both views render stacked, which is a complete page rather than a broken one —
    the switch is an enhancement, not the mechanism.
    """
    links = [
        f'<a class=file href="{html.escape(_RECORD_MEMBER)}" download>'
        f"{html.escape(_RECORD_MEMBER)}</a>"
    ]
    if artifact and artifact.path:
        links.insert(
            0,
            f'<a class=file href="{html.escape(artifact.name)}" download>'
            f"{html.escape(artifact.name)}</a>",
        )
    return (
        "<nav class=tabs>"
        '<button type=button class="tab on" data-view=read>reading view</button>'
        '<button type=button class=tab data-view=src>record source</button>'
        f"<span class=spacer></span>{''.join(links)}"
        "</nav>"
    )


# Enhancement only: without it, `body` carries no `data-view` and the CSS leaves both views
# visible. An in-page jump from a source-view address has to switch back to the reading view
# first, or the link would silently scroll a hidden element — hence the hashchange handler.
_TABS_JS = """<script>
(function () {
  var body = document.body, tabs = document.querySelectorAll('.tab');
  function show(view) {
    body.setAttribute('data-view', view);
    tabs.forEach(function (t) { t.classList.toggle('on', t.dataset.view === view); });
  }
  tabs.forEach(function (t) {
    t.addEventListener('click', function () { show(t.dataset.view); });
  });
  function follow() {
    if (!location.hash) return;
    var target = document.querySelector(location.hash);
    if (!target) return;
    show(target.closest('#view-src') ? 'src' : 'read');
    target.scrollIntoView();
  }
  window.addEventListener('hashchange', follow);
  show('read');
  follow();
})();
</script>"""


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
    root: Path,
    record_id: str,
    member: dict[str, Any],
    *,
    regenerate: bool,
    budget: _Budget,
    claimed: set[str],
) -> str:
    """One member rendered with its bytes — for the two cases that have nowhere else to show:
    a container whose roster IS its content, and an unplaced asset."""
    address = member.get("address")
    anchor, aliases = _anchor_targets(_addr_list(address), claimed)
    out = [
        f"<div class=block{anchor}>{aliases}"
        f"<h3>{html.escape(str(address))} "
        f"<span class=tag>{html.escape(str(member.get('media_type') or ''))}</span></h3>"
    ]
    path, err = _resolve_surface(root, record_id, address, regenerate=regenerate)
    out.append(_surface_html(path, budget) if path else _note(err or "no address"))
    out.append("</div>")
    return "\n".join(out)


class _PlacedMember:
    """*(3.8)* One member a record places, and where a reader goes to read it.

    The whole chain is derived (§4.3.2.4): the placement's address matches exactly one roster
    row, that row's `transport:` IS the member's record id (§2), and the record's path is a
    pure function of the id. Nothing here is stored on either record — which is the point, and
    also why the page can show it: it shows what a reader would follow.
    """

    def __init__(self, address: str, hexval: str, record: Path | None, state: str) -> None:
        self.address = address
        self.hex = hexval
        self.record = record
        self.state = state
        #: Relative href into the bundle, set when the member's page is bundled alongside.
        self.href: str | None = None

    @property
    def label(self) -> str:
        if self.record is None:
            return f"member {self.hex[:12]}… — NO RECORD"
        return f"member {self.hex[:12]}… ({self.state})"


def placed_members(root: Path, post: Any) -> dict[str, _PlacedMember]:
    """*(3.8)* `placement address → the member it names`, for every placement in the content
    zone. Ordered by first appearance, so a bundle's member pages come in reading order."""
    try:
        blocks = segments.iter_blocks(post.content or "")
    except Exception:
        return {}
    rows: dict[str, str] = {}
    for row in records.iter_members(post):
        hexval = str(row.get("transport") or "").partition(":")[2]
        for addr in _addr_list(row.get("address")):
            if hexval:
                rows[addr] = hexval
    out: dict[str, _PlacedMember] = {}
    for blk in blocks:
        kids = blk.segments if isinstance(blk, segments.Section) else [blk]
        for seg in kids:
            if not isinstance(seg, segments.Segment) or not seg.is_placement:
                continue
            for addr in _addr_list(seg.address):
                # A DECONSTRUCTED placement chains the member's address with one of the leaf's
                # own segment addresses (§4.3.2.4), so the MEMBER is named by the base. Keyed
                # by the base, so N deconstructed placements share one member page.
                addr = addr.split("&", 1)[0]
                hexval = rows.get(addr)
                if not hexval or addr in out:
                    continue
                leaf = paths.record_path(root, hexval)
                if not leaf.is_file():
                    out[addr] = _PlacedMember(addr, hexval, None, "")
                    continue
                try:
                    state = records.derived_state(records.load(leaf), root)
                except Exception:
                    state = "?"
                out[addr] = _PlacedMember(addr, hexval, leaf, state)
    return out


def _imported_html(
    member: _PlacedMember | None,
    *,
    root: Path,
    regenerate: bool,
    budget: _Budget,
    region: str | None = None,
) -> str:
    """*(3.8)* The IMPORT — the member's own rendering, shown where the parent places it.

    §4.3.2.4 says the rendering is imported, and a viewer that showed only the resolved pixels
    was showing the one thing the parent still has and withholding the one thing the member
    added. For a table image that is the whole point: the reader wants the table, and it lives
    on the leaf now. Attributed to its record rather than presented as the parent's own, since
    that distinction is exactly what the amendment introduced — and derived on every render, so
    it cannot go stale against the record it reads.

    **A body-empty marker IS a rendering.** The first cut required a non-empty body, which
    silently excluded the one shape a leaf uses to say *this region is a figure* (§4.3.2.2's
    body-empty positioning marker) — so a leaf that had divided its artifact into regions
    imported as nothing, and the parent fell back to showing the undivided member image. The
    marker's content is its resolved region, so it resolves here against the MEMBER's own id:
    the leaf's addresses are relative to the leaf's bytes, which is exactly what makes them
    re-homeable in the first place (§4.3.1.4).

    Structural marks ride along, because the import is meant to read the way the leaf reads and
    a mark is how the leaf carries a heading it did not invent (§4.3.2.3).

    A member with no rendering at all still says so: that is honest demand (normalization
    pressure, §8.5), not an empty block.

    `region` is the DECONSTRUCTED import (§4.3.2.4): the chained suffix off the placement's
    address, naming one address the leaf declares. Only the leaf segments at that address are
    imported — all of them, since the grain is the address rather than the segment (a `text`
    and a `text/data-table` over one region legitimately share an address). `None` imports the
    leaf whole, which is the ordinary form.
    """
    if member is None or member.record is None:
        return ""
    try:
        post = records.load(member.record)
        blocks = segments.iter_blocks(post.content or "")
    except Exception:
        return ""
    segs = [
        seg
        for blk in blocks
        for seg in (blk.segments if isinstance(blk, segments.Section) else [blk])
        if isinstance(seg, segments.Segment)
        and (seg.is_content or seg.is_structural)
        and (seg.address or (seg.body or "").strip())
        and (region is None or region in _addr_list(seg.address))
    ]
    where = (
        f'<a href="{html.escape(member.href)}">{html.escape(member.hex[:12])}…</a>'
        if member.href
        else f"{html.escape(member.hex[:12])}…"
    )
    if not segs:
        return _note(f"member {member.hex[:12]}… carries no rendering yet — its own pass is owed")
    parts = [f'<div class=imported><p class=sub>imported from {where}</p>']
    for seg in segs:
        tag = f' <span class=tag>{html.escape(_address_tag(seg.address))}</span>'
        if seg.is_structural:
            parts.append(f"<h4>{html.escape((seg.body or '').strip())}{tag}</h4>")
            continue
        parts.append(f"<h4>{html.escape(seg.overlay or seg.atom or '')}{tag}</h4>")
        if (seg.body or "").strip():
            parts.append(_body_html(seg.body))
        elif region is None:
            # The marker's content is the region it names — resolved against the LEAF.
            parts.append(
                _placement_surface(
                    root, member.hex, seg, regenerate=regenerate, budget=budget
                )
            )
        # Under a DECONSTRUCTED import the placement already resolved this exact region — its
        # own address chains to this one — so re-resolving would inline the same pixels twice.
        # The heading still lands: it is the leaf saying it read this region and called it a
        # figure, which the pixels immediately above do not say on their own.
    parts.append("</div>")
    return "\n".join(parts)


def _placement_surface(
    root: Path,
    record_id: str,
    seg: segments.Segment,
    *,
    regenerate: bool,
    budget: _Budget,
) -> str:
    path, err = _resolve_surface(root, record_id, seg.address, regenerate=regenerate)
    if path:
        return _surface_html(path, budget)
    return _note(f"address does not resolve — {err}") if err else ""


def _segment_html(
    root: Path,
    record_id: str,
    seg: segments.Segment,
    *,
    regenerate: bool,
    budget: _Budget,
    claimed: set[str],
    leaves: dict[str, _PlacedMember] | None = None,
) -> str:
    anchor, aliases = _anchor_targets(_addr_list(getattr(seg, "address", None)), claimed)
    if seg.is_structural:
        # A byte-mark's BODY is the SOURCE's own heading text (§4.3.2.3, 3.8 — a `mark:`
        # field before §12.32) — the most informative thing about the mark, so it leads.
        # Rendered, not escaped-flat: the whole point of the move is that a heading may
        # carry links, and a view that flattened them would hide exactly what was recovered.
        label = f" {_body_html(seg.body)}" if (seg.body or "").strip() else ""
        level = f" <span class=tag>level {seg.level}</span>" if getattr(seg, "level", None) else ""
        return (f"<div class=block{anchor}>{aliases}<h3>structural mark{label} "
                f"<span class=tag>{html.escape(_address_tag(seg.address))}</span>{level}</h3></div>")
    if seg.is_placement:
        # *(3.8)* A placement says a member sits here and nothing else (§4.3.2.4), so the view's
        # job is to make the IMPORT visible: the surface resolves from this record's bytes as
        # before, and the member's own record is named as the place its reading lives. The link
        # is DERIVED here exactly as everywhere — address → roster row → blake3 → record — so
        # the page shows what a reader would follow, never a stored pointer.
        member = None
        region: str | None = None
        for addr in _addr_list(seg.address):
            base, sep, suffix = addr.partition("&")
            member = (leaves or {}).get(base)
            if member:
                region = suffix if sep else None
                break
        tag = ""
        if member:
            body = html.escape(member.label)
            # Linked when the member's page rides in the same bundle; named-only otherwise,
            # with the recovery line below saying how to reach it. Never a dead href.
            tag = (
                f' <a class="tag member" href="{html.escape(member.href)}">{body}</a>'
                if member.href
                else f" <span class=tag>{body}</span>"
            )
        recovery = ""
        if member and member.record is not None and not member.href:
            recovery = _note(f"read it: corpus view {member.hex}")
        return "\n".join(
            [
                f"<div class=block{anchor}>{aliases}",
                f"<h3>placement <span class=tag>{html.escape(_address_tag(seg.address))}</span>"
                + tag
                + "</h3>",
                _placement_surface(root, record_id, seg, regenerate=regenerate, budget=budget),
                _imported_html(
                    member, root=root, regenerate=regenerate, budget=budget, region=region
                ),
                recovery,
                "</div>",
            ]
        )
    parts = [f"<div class=block{anchor}>{aliases}"
             f"<h3>{html.escape(_segment_id(seg))} "
             f"<span class=tag>{html.escape(_address_tag(seg.address))}</span>"
             # `entry` is a DEDICATED field, not part of `extra`, so iterating `extra` alone
             # rendered nothing for it. It is this corpus's only way to label a block inside a
             # whole-record form span (spec §4.3.2.2) — 11,516 segments across 4,380 records
             # carry one — so a reading view blind to it shows a run of anonymous tables and
             # silently contradicts the authoring it is meant to display.
             + (f' <span class="tag entry">{html.escape(str(seg.entry))}</span>'
                if getattr(seg, "entry", None) else "")
             + "</h3>"]
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
/* *(3.8)* The IMPORT: a member's own rendering, shown where the parent places it. Set
   apart deliberately — it is another record's content, and the whole amendment is about
   that distinction being visible rather than assumed. */
.imported { border-left:3px solid var(--acc); padding:.4rem 0 .4rem .9rem; margin:.8rem 0; }
.imported > .sub { margin:0 0 .5rem; }
.imported h4 { margin:.6rem 0 .3rem; font-size:.9rem; font-weight:600; }
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

/* view switch. No `data-view` on <body> (script absent/blocked) leaves BOTH views visible —
   a complete page, just not a tabbed one. */
.tabs { display:flex; align-items:center; gap:.5rem; flex-wrap:wrap; margin:1rem 0 0;
  padding-bottom:.6rem; border-bottom:1px solid var(--line); }
.tabs .spacer { flex:1 1 auto; }
button.tab { font:inherit; font-size:.8rem; color:var(--mut); background:transparent;
  border:1px solid var(--line); border-radius:4px; padding:.3rem .7rem; cursor:pointer; }
button.tab.on { color:var(--bg); background:var(--acc); border-color:var(--acc); }
a.file { font-size:.78rem; font-family:ui-monospace, SFMono-Regular, monospace;
  color:var(--acc); text-decoration:none; border:1px solid var(--line);
  border-radius:4px; padding:.3rem .55rem; }
a.file:hover { border-color:var(--acc); }
body[data-view=read] #view-src, body[data-view=src] #view-read { display:none; }

/* record source. `.ln` is display:block so the line number can hang in ::before — which also
   keeps it OUT of a copy-paste of the record, unlike a real column would be. */
pre.src { background:var(--card); border:1px solid var(--line); border-radius:4px;
  padding:.7rem 0; overflow-x:auto; font-size:.82rem; line-height:1.5; margin:.75rem 0; }
pre.src .ln { display:block; position:relative; padding:0 .9rem 0 4.4rem;
  white-space:pre-wrap; word-break:break-word; }
pre.src .ln::before { content:attr(data-n); position:absolute; left:0; width:3.4rem;
  text-align:right; color:var(--mut); opacity:.6; user-select:none; }
pre.src .ln:target { background:color-mix(in srgb, var(--acc) 16%, transparent); }
pre.src .cm { color:var(--mut); }
pre.src a.addr { color:var(--acc); text-decoration:underline;
  text-decoration-style:dotted; text-underline-offset:2px; }
.alias { display:block; height:0; }
.block:target, .alias:target + h3 { outline:2px solid var(--acc); outline-offset:3px; }
</style>"""
