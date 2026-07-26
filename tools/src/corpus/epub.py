"""EPUB container reader (pure: zip + OPF parsing, no draft/LLM concerns).

An EPUB is a zip whose `META-INF/container.xml` points at an OPF package document.
The OPF declares the publication `<metadata>` (Dublin Core), a `<manifest>` of every
member (XHTML content docs, CSS, images, fonts), and a `<spine>` giving the reading
order as an ordered list of `<itemref idref=...>`.

This module reads that structure into an `EpubPackage` (publication metadata + the
ordered spine content documents) and offers two text helpers. It imports only the
stdlib + BeautifulSoup, so it pulls in no `draft`/`content_hash` dependency — both the
epub drafter (`draft/epub.py`) and the `blake3-canonical-epub` strategy
(`content_hash.py`) import it without an import cycle through `draft/__init__`.
"""

from __future__ import annotations

import io
import posixpath
import re
import warnings
import zipfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import blake3 as _blake3
from bs4 import BeautifulSoup, Comment, Tag, XMLParsedAsHTMLWarning
from PIL import Image


def _soup(data: bytes | str) -> BeautifulSoup:
    """Parse with `html.parser` (no lxml dependency, same as the HTML drafter), silencing
    bs4's "you used an HTML parser on XML" advisory — EPUB's OPF + XHTML are XML and we
    deliberately accept the leniency. The local `catch_warnings` survives pytest's
    per-test warning-capture reset, unlike a module-level `filterwarnings`."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", XMLParsedAsHTMLWarning)
        return BeautifulSoup(data, "html.parser")


_CONTAINER_PATH = "META-INF/container.xml"

# Dublin Core metadata keys lifted from the OPF `<metadata>` block.
_DC_KEYS = (
    "title", "creator", "language", "publisher", "date", "identifier",
)

# XHTML cleaning — non-rendered infrastructure stripped. `<img>` is KEPT (it references a
# separately-stored zip member → an embed, like an HTML `<img>` decoded from a data URI);
# inline `<svg>` is dropped (v2 embeds referenced raster images only).
_STRIP_TAGS = {"script", "style", "noscript", "template", "link", "head", "svg"}
_UNWRAP_TAGS = {"div", "span"}
_KEEP_ATTRS: dict[str, set[str]] = {
    "a": {"href"},
    "img": {"alt"},
    "td": {"colspan", "rowspan"},
    "th": {"colspan", "rowspan"},
    "ol": {"start", "type"},
    "li": {"value"},
}
# `data-el` is the drafter's element-position annotation (the embed address sub-key);
# kept globally like `id`.
_GLOBAL_KEEP_ATTRS = {"id", "data-el"}
_EXCESS_NEWLINE_RE = re.compile(r"\n{3,}")

# Addressable elements get a 1-indexed `el` position in document order — the same axis the
# HTML drafter uses, so an image's address (`spine=<N>&el=<K>`) is consistent across formats.
# Kept identical to `corpus.draft.html._ADDRESSABLE_TAGS`; `test_drafters.py` asserts lockstep.
_ADDRESSABLE_TAGS = (
    "section", "article", "p", "ul", "ol", "dl", "table",
    "pre", "blockquote", "figure",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "img",
)

# Zip-member extensions treated as image resources, and their MIME types (derived from the
# `<img src>` extension — robust and avoids format-sniff quirks).
_IMG_MEDIA = {
    "png": "image/png", "jpg": "image/jpeg", "jpeg": "image/jpeg", "gif": "image/gif",
    "svg": "image/svg+xml", "webp": "image/webp", "bmp": "image/bmp",
    "tif": "image/tiff", "tiff": "image/tiff",
}


@dataclass
class SpineDoc:
    """One content document in spine (reading) order."""

    href: str  # zip member path (resolved against the OPF directory)
    media_type: str
    data: bytes


@dataclass
class TocEntry:
    """One top-level navigation (table-of-contents) entry, mapped to the spine index of
    its target content document (1-based)."""

    title: str
    spine_index: int


@dataclass
class EpubPackage:
    metadata: dict[str, str]
    spine: list[SpineDoc]
    toc: list[TocEntry]


def read_package(path: Path) -> EpubPackage:
    """Parse an EPUB into its publication metadata + ordered spine documents.

    Tolerant: a malformed container / missing OPF / unreadable spine item yields an
    empty-or-partial package rather than raising — the drafter surfaces emptiness as an
    issue, never a crash (parse tolerantly, spec §1.5)."""
    try:
        with zipfile.ZipFile(path) as zf:
            opf_path = _opf_path(zf)
            if not opf_path:
                return EpubPackage(metadata={}, spine=[], toc=[])
            try:
                opf_raw = zf.read(opf_path)
            except KeyError:
                return EpubPackage(metadata={}, spine=[], toc=[])
            soup = _soup(opf_raw)
            opf_dir = posixpath.dirname(opf_path)
            metadata = _read_metadata(soup)
            manifest = _read_manifest(soup)
            spine = _read_spine(soup, manifest, opf_dir, zf)
            spine_index = {doc.href: i for i, doc in enumerate(spine, start=1)}
            toc = _read_toc(soup, opf_dir, zf, spine_index)
            return EpubPackage(metadata=metadata, spine=spine, toc=toc)
    except zipfile.BadZipFile:
        return EpubPackage(metadata={}, spine=[], toc=[])


def spine_text(path: Path) -> str:
    """Concatenated visible text of every spine document, in reading order — the basis
    for the `blake3-canonical-epub` content identity (drops zip packaging, timestamps,
    and CSS/scripts, keeping only the prose)."""
    chunks: list[str] = []
    for doc in read_package(path).spine:
        soup = _soup(doc.data)
        for tag in soup.find_all(["script", "style"]):
            tag.decompose()
        chunks.append(soup.get_text(" ", strip=True))
    return "\n\n".join(chunks)


def clean_xhtml_body(
    raw: bytes, *, image_resolver: Callable[[str], bytes | None] | None = None
) -> tuple[str, list[dict]]:
    """Mechanically clean one spine document's XHTML to structural body HTML and extract
    its image embeds. Returns `(cleaned_html, embeds)`.

    Same mechanical philosophy as the HTML drafter: strip non-rendered infrastructure,
    keep structure (headings, prose, lists, tables), never guess at chrome, leave rendering
    to the normalizer. Addressable elements get a 1-indexed `el` in document order.

    `image_resolver(src) -> bytes | None` resolves an `<img src>` (a path relative to the
    spine document) to its zip-member bytes. Each resolvable `<img>` is kept in the body as
    an addressable `<img data-el="K">` placeholder (its `src` stripped — the bytes are
    addressed via the embed) and yields an embed dict `{media_type, byte_hash, width,
    height, alt, els}` (deduped by `byte_hash` within the document; `els` lists every
    position the same bytes appear). Unresolvable images (no resolver / missing member) are
    dropped from the body, like the HTML drafter drops a chrome-stripped image."""
    soup = _soup(raw)
    _strip_non_addressable(soup)

    # Pre-pass over the pre-strip tree: assign el-indices and resolve image embeds.
    el_by_id: dict[int, int] = {}
    kept_img_ids: set[int] = set()
    embed_by_hash: dict[str, dict] = {}
    for n, tag in enumerate(soup.find_all(_ADDRESSABLE_TAGS), start=1):
        if not isinstance(tag, Tag):
            continue
        el_by_id[id(tag)] = n
        if tag.name == "img":
            meta = _img_embed_meta(tag, image_resolver)
            if meta is None:
                continue
            kept_img_ids.add(id(tag))
            slot = embed_by_hash.setdefault(
                meta["byte_hash"],
                {k: meta[k] for k in ("media_type", "byte_hash", "width", "height", "alt")}
                | {"els": []},
            )
            slot["els"].append(n)

    _annotate_addressable(soup, el_by_id, kept_img_ids)
    _strip_attrs(soup)
    _unwrap_empty(soup)
    root = soup.find("body") or soup
    html = _EXCESS_NEWLINE_RE.sub("\n\n", str(root)).strip()
    return html, list(embed_by_hash.values())


def read_resources(path: Path) -> dict[str, bytes]:
    """Map every image zip-member path → its bytes (the EPUB's separately-stored assets the
    drafter turns into embeds). Tolerant: a bad zip / unreadable member is skipped."""
    out: dict[str, bytes] = {}
    try:
        with zipfile.ZipFile(path) as zf:
            for name in zf.namelist():
                ext = name.rsplit(".", 1)[-1].lower() if "." in name else ""
                if ext in _IMG_MEDIA:
                    try:
                        out[name] = zf.read(name)
                    except KeyError:
                        continue
    except zipfile.BadZipFile:
        pass
    return out


def make_image_resolver(
    resources: dict[str, bytes], doc_href: str
) -> Callable[[str], bytes | None]:
    """A resolver that maps an `<img src>` (relative to the spine document `doc_href`) to
    its bytes in `resources` — resolving `../`, dropping any `#fragment`/`?query`."""
    base = posixpath.dirname(doc_href)

    def resolve(src: str) -> bytes | None:
        clean = src.split("#", 1)[0].split("?", 1)[0].strip()
        if not clean:
            return None
        member = posixpath.normpath(posixpath.join(base, clean)) if base else clean
        return resources.get(member)

    return resolve


def addressable_element_count(raw: bytes) -> int:
    """How many `el=K` positions a spine document's raw XHTML has — the same strip and
    the same tag set `addressable_image_bytes` counts, so a bounds check taken from here
    agrees with the one materialization applies. Exists so a SPAN address (`el=4-9`) can
    be held to the element list even though it never materializes."""
    soup = _soup(raw)
    _strip_non_addressable(soup)
    return len([t for t in soup.find_all(_ADDRESSABLE_TAGS) if isinstance(t, Tag)])


def addressable_image_bytes(
    raw: bytes, el: int, resolve_img: Callable[[str], bytes | None]
) -> bytes:
    """The zip-member bytes of the `<img>` at addressable position `el` (1-indexed,
    document order) in a spine document's raw XHTML — the materialization side of a
    `spine=<N>&el=<K>` embed address (the inverse of what `clean_xhtml_body` recorded).

    El-indexing matches the drafter EXACTLY: the same non-addressable strip is applied
    before counting `_ADDRESSABLE_TAGS`, so the `K` the drafter wrote into the embed
    address (and the `<img data-el="K">` placeholder) selects the same element here.
    Raises `ValueError` on a bad index, a non-`<img>` element, or an unresolvable src."""
    soup = _soup(raw)
    _strip_non_addressable(soup)
    elements = [t for t in soup.find_all(_ADDRESSABLE_TAGS) if isinstance(t, Tag)]
    if el < 1 or el > len(elements):
        raise ValueError(
            f"el={el} out of range (spine document has {len(elements)} addressable elements)"
        )
    tag = elements[el - 1]
    if tag.name != "img":
        raise ValueError(
            f"el={el} resolved to <{tag.name}>, expected <img>; "
            f"only image embeds are materializable via el="
        )
    src = str(tag.get("src") or "").strip()
    if not src:
        raise ValueError(f"el={el} <img> has no src to resolve")
    data = resolve_img(src)
    if not data:
        raise ValueError(
            f"el={el} <img src={src!r}> did not resolve to a zip member"
        )
    return data


def document_title(raw: bytes) -> str:
    """A spine document's own title: the `<title>` element, else its first heading."""
    soup = _soup(raw)
    if (tag := soup.find("title")) and tag.get_text(strip=True):
        return tag.get_text(strip=True)
    if (h := soup.find(["h1", "h2", "h3", "h4", "h5", "h6"])) and h.get_text(strip=True):
        return " ".join(h.get_text(" ", strip=True).split())
    return ""


# ---------- OPF parsing ---------- #


def _opf_path(zf: zipfile.ZipFile) -> str | None:
    try:
        raw = zf.read(_CONTAINER_PATH)
    except KeyError:
        return None
    soup = _soup(raw)
    rootfile = soup.find("rootfile")
    if isinstance(rootfile, Tag) and rootfile.get("full-path"):
        return str(rootfile.get("full-path")).strip()
    return None


def _read_metadata(soup: BeautifulSoup) -> dict[str, str]:
    md = soup.find("metadata")
    out: dict[str, str] = {}
    if not isinstance(md, Tag):
        return out
    for key in _DC_KEYS:
        tag = md.find(f"dc:{key}")
        if isinstance(tag, Tag) and tag.get_text(strip=True):
            out[key] = " ".join(tag.get_text(" ", strip=True).split())
    return out


def _read_manifest(soup: BeautifulSoup) -> dict[str, tuple[str, str]]:
    """id -> (href, media_type) for every `<manifest><item>`."""
    out: dict[str, tuple[str, str]] = {}
    man = soup.find("manifest")
    if not isinstance(man, Tag):
        return out
    for item in man.find_all("item"):
        iid = item.get("id")
        href = item.get("href")
        if iid and href:
            out[str(iid)] = (str(href), str(item.get("media-type") or ""))
    return out


def _read_spine(
    soup: BeautifulSoup,
    manifest: dict[str, tuple[str, str]],
    opf_dir: str,
    zf: zipfile.ZipFile,
) -> list[SpineDoc]:
    spine = soup.find("spine")
    if not isinstance(spine, Tag):
        return []
    names = set(zf.namelist())
    docs: list[SpineDoc] = []
    for itemref in spine.find_all("itemref"):
        idref = itemref.get("idref")
        if not idref or str(idref) not in manifest:
            continue
        href, media_type = manifest[str(idref)]
        full = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
        if full not in names:
            continue
        try:
            data = zf.read(full)
        except KeyError:
            continue
        docs.append(SpineDoc(href=full, media_type=media_type, data=data))
    return docs


# ---------- navigation (table of contents) ---------- #


def _read_toc(
    soup: BeautifulSoup,
    opf_dir: str,
    zf: zipfile.ZipFile,
    spine_index: dict[str, int],
) -> list[TocEntry]:
    """Top-level TOC entries, each mapped to the spine index of its target content
    document. Prefers the EPUB 3 nav document (`<item properties="nav">`), falling back to
    the EPUB 2 NCX (`application/x-dtbncx+xml`). Empty when neither is present/parseable —
    the drafter then emits a flat (sectionless) body. Only **top-level** entries are read;
    deeper nesting is intra-document sub-structure the normalizer recovers as prose
    headings (mirrors the PDF drafter's `get_toc(max_depth=1)`)."""
    raw = _nav_entries(soup, opf_dir, zf) or _ncx_entries(soup, opf_dir, zf)
    return _resolve_toc(raw, opf_dir, spine_index)


def _manifest_items(soup: BeautifulSoup) -> list[Tag]:
    man = soup.find("manifest")
    return [i for i in man.find_all("item") if isinstance(i, Tag)] if isinstance(man, Tag) else []


def _nav_entries(soup: BeautifulSoup, opf_dir: str, zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """EPUB 3 nav document → top-level `(title, href)` of the `toc` nav's outer `<ol>`."""
    nav_href = next(
        (
            str(item.get("href"))
            for item in _manifest_items(soup)
            if "nav" in (item.get("properties") or "").split() and item.get("href")
        ),
        None,
    )
    if not nav_href:
        return []
    nav = _read_member_soup(zf, opf_dir, nav_href)
    if nav is None:
        return []
    toc = next(
        (n for n in nav.find_all("nav") if isinstance(n, Tag) and n.get("epub:type") == "toc"),
        nav.find("nav"),
    )
    ol = toc.find("ol") if isinstance(toc, Tag) else None
    if not isinstance(ol, Tag):
        return []
    out: list[tuple[str, str]] = []
    for li in ol.find_all("li", recursive=False):
        a = li.find("a")
        if isinstance(a, Tag) and a.get("href") and a.get_text(strip=True):
            out.append((" ".join(a.get_text(" ", strip=True).split()), str(a.get("href"))))
    return out


def _ncx_entries(soup: BeautifulSoup, opf_dir: str, zf: zipfile.ZipFile) -> list[tuple[str, str]]:
    """EPUB 2 NCX → top-level `(title, src)` of `<navMap>`'s direct `<navPoint>` children."""
    ncx_href = next(
        (
            str(item.get("href"))
            for item in _manifest_items(soup)
            if (item.get("media-type") or "") == "application/x-dtbncx+xml" and item.get("href")
        ),
        None,
    )
    if not ncx_href:
        return []
    ncx = _read_member_soup(zf, opf_dir, ncx_href)
    if ncx is None:
        return []
    navmap = ncx.find("navmap")
    if not isinstance(navmap, Tag):
        return []
    out: list[tuple[str, str]] = []
    for point in navmap.find_all("navpoint", recursive=False):
        label = point.find("navlabel")
        content = point.find("content")
        if (
            isinstance(label, Tag)
            and isinstance(content, Tag)
            and content.get("src")
            and label.get_text(strip=True)
        ):
            out.append((" ".join(label.get_text(" ", strip=True).split()), str(content.get("src"))))
    return out


def _resolve_toc(
    raw: list[tuple[str, str]], opf_dir: str, spine_index: dict[str, int]
) -> list[TocEntry]:
    """Map each `(title, href)` to its target document's spine index, dropping the link
    fragment, skipping targets not in the spine, and collapsing entries that don't advance
    the spine position (two TOC links into the same document → one section boundary)."""
    out: list[TocEntry] = []
    for title, href in raw:
        doc = href.split("#", 1)[0]
        if not doc:
            continue
        full = posixpath.normpath(posixpath.join(opf_dir, doc)) if opf_dir else doc
        idx = spine_index.get(full)
        if idx is None or (out and idx <= out[-1].spine_index):
            continue
        out.append(TocEntry(title=title, spine_index=idx))
    return out


def _read_member_soup(zf: zipfile.ZipFile, opf_dir: str, href: str) -> BeautifulSoup | None:
    full = posixpath.normpath(posixpath.join(opf_dir, href)) if opf_dir else href
    try:
        return _soup(zf.read(full))
    except KeyError:
        return None


# ---------- XHTML cleaning helpers ---------- #


def _strip_non_addressable(soup: BeautifulSoup) -> None:
    """Remove non-rendered infrastructure (`_STRIP_TAGS`) and comments, in place. Applied
    before el-indexing by BOTH the drafter (`clean_xhtml_body`) and the resolver
    (`addressable_image_bytes`) so their `_ADDRESSABLE_TAGS` counts agree — a `<noscript>`-
    or `<svg>`-wrapped element must not shift the index on one side only."""
    for tag in soup.find_all(_STRIP_TAGS):
        tag.decompose()
    for comment in list(soup.find_all(string=lambda s: isinstance(s, Comment))):
        comment.extract()


def _img_embed_meta(
    tag: Tag, image_resolver: Callable[[str], bytes | None] | None
) -> dict | None:
    """Resolve an `<img>` to its zip-member bytes and compute embed metadata
    `{media_type, byte_hash, width, height, alt}`, or None when there's no resolver / the
    src is empty or unresolvable. `byte_hash` is the full blake3 hexdigest of the member
    bytes (the transport / dedup key); dimensions come from PIL (0 when unreadable, e.g.
    SVG). `media_type` is derived from the src extension."""
    if image_resolver is None:
        return None
    src = str(tag.get("src") or "").strip()
    if not src:
        return None
    data = image_resolver(src)
    if not data:
        return None
    ext = src.split("#", 1)[0].split("?", 1)[0].rsplit(".", 1)[-1].lower()
    width = height = 0
    try:
        with Image.open(io.BytesIO(data)) as im:
            width, height = im.size
    except Exception:
        pass
    return {
        "media_type": _IMG_MEDIA.get(ext, "application/octet-stream"),
        "byte_hash": _blake3.blake3(data).hexdigest(),
        "width": width,
        "height": height,
        "alt": str(tag.get("alt") or "").strip(),
    }


def _annotate_addressable(
    soup: BeautifulSoup, el_by_id: dict[int, int], kept_img_ids: set[int]
) -> None:
    """Strip each embedded `<img>` of its `src`/`srcset` and tag it with its `data-el`
    position (the embed address sub-key); drop images that produced no embed (unresolvable
    src). Non-image elements keep their el position implicitly (numbered in the pre-pass);
    only embedded images carry an explicit `data-el` address."""
    for tag in soup.find_all("img"):
        if not isinstance(tag, Tag):
            continue
        if id(tag) not in kept_img_ids:
            tag.decompose()
            continue
        for attr in ("src", "srcset"):
            if attr in tag.attrs:
                del tag.attrs[attr]
        if idx := el_by_id.get(id(tag)):
            tag["data-el"] = str(idx)


def _strip_attrs(soup: BeautifulSoup) -> None:
    for tag in soup.find_all(True):
        if not isinstance(tag, Tag) or not tag.attrs:
            continue
        keep = _KEEP_ATTRS.get(tag.name, set()) | _GLOBAL_KEEP_ATTRS
        for attr in list(tag.attrs.keys()):
            if attr not in keep:
                del tag.attrs[attr]


def _unwrap_empty(soup: BeautifulSoup) -> None:
    while True:
        candidates = [
            t for t in soup.find_all(True)
            if isinstance(t, Tag) and t.name in _UNWRAP_TAGS and not t.attrs
        ]
        if not candidates:
            break
        for t in candidates:
            t.unwrap()
