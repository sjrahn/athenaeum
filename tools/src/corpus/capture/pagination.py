"""Pagination reconciliation — walk a paginated work's pages, merge them into one HTML.

A paginated thread / multi-page article / gallery is **one logical artifact** that a site
splits across ``?page=N`` / ``/page-N`` URLs. The capture pipeline stages each page (the
orchestration lives in ``capture/__init__._reconcile_pagination``); this module holds the
pure, browser-free logic it drives:

- ``normalize_config`` — read the overlay's ``capture.pagination`` knob (bare ``true`` or a map).
- ``extract_next_url`` — find the next page (``<link/a rel=next>`` or a CSS override).
- ``detect_region`` / ``locate_region`` — find the per-page content region to concatenate
  (structural auto-detect when no ``content_selector`` is declared).
- ``merge_pages`` — append later pages' content children into page 1's region, deduped by
  element id (or a normalized-subtree hash for id-less nodes).
- ``expected_count`` — read a site-advertised item count for the completeness check.

Everything here operates on HTML strings via BeautifulSoup — no browser, no I/O — so the
merge is unit-testable. The INVARIANT (the retired PAGINATION-RECONCILE doc, restated
here): only the merged document is content-addressed; per-page captures are transient.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from .. import urls as urlcanon

log = logging.getLogger("corpus.capture.pagination")

# `<img>` lazy-load attributes promoted to `src` on merged-in nodes (best-effort, so the
# capture's image pre-fetch / the drafter's embed extraction sees a real URL).
_LAZY_SRC_ATTRS = ("data-src", "data-lazy-src", "data-original")

# A region path is a list of (node-signature, index-among-same-signature-siblings) steps
# from <body> down to the content region — stable across pages because the framing
# (ancestors of the content region) is identical page to page.
RegionPath = list[tuple[str, int]]


@dataclass(frozen=True)
class PaginationConfig:
    """Resolved `capture.pagination` knob. See `normalize_config`."""

    content_selector: str | None = None  # declared per-page content region (else auto-detect)
    follow_rel: bool = True  # follow <link rel=next> / <a rel=next>
    next_selector: str | None = None  # CSS override for the next-page link
    max_pages: int = 100  # safety cap (don't silently truncate: flag if hit)
    expect_selector: str | None = None  # element whose text holds the advertised item count


def normalize_config(raw: Any) -> PaginationConfig | None:
    """Resolve the overlay's `capture.pagination` value to a `PaginationConfig`.

    `True` → all defaults (auto-detect everything). A map → its keys (`content_selector`,
    `next.rel`/`next.selector`, `max_pages`, `expect_count.selector`). Anything falsy or
    malformed (`False`, `None`, a scalar) → None (pagination disabled — the normal
    single-page path).
    """
    if raw is True:
        return PaginationConfig()
    if not isinstance(raw, dict):
        return None

    nxt = raw.get("next")
    nxt = nxt if isinstance(nxt, dict) else {}
    expect = raw.get("expect_count")
    expect = expect if isinstance(expect, dict) else {}

    try:
        max_pages = int(raw.get("max_pages", 100))
    except (TypeError, ValueError):
        max_pages = 100

    next_selector = nxt.get("selector")
    expect_selector = expect.get("selector")
    return PaginationConfig(
        content_selector=(str(raw["content_selector"]) if raw.get("content_selector") else None),
        follow_rel=bool(nxt.get("rel", True)),
        next_selector=(str(next_selector) if next_selector else None),
        max_pages=max(1, max_pages),
        expect_selector=(str(expect_selector) if expect_selector else None),
    )


# ---------- next-page enumeration ---------- #


def extract_next_url(html: str, *, base_url: str, cfg: PaginationConfig) -> str | None:
    """Return the absolute, normalized URL of the page that follows `html`, or None.

    Order: `<link rel=next>` (lives in `<head>`, so it survives the `remove:` chrome strip),
    then `<a rel=next>`, then `cfg.next_selector`. The href is resolved against `base_url`
    and normalized; the **bare site form** is returned (the caller pins it via `url_rewrite`).
    """
    soup = BeautifulSoup(html, "html.parser")
    href: str | None = None
    if cfg.follow_rel:
        href = _rel_next_href(soup)
    if not href and cfg.next_selector:
        el = soup.select_one(cfg.next_selector)
        if isinstance(el, Tag):
            href = el.get("href")
    if not href:
        return None
    href = str(href).strip()
    if not href or not urlcanon.is_crawlable_href(href):
        return None
    try:
        return urlcanon.normalize(urljoin(base_url, href))
    except ValueError:
        return None


def _rel_next_href(soup: BeautifulSoup) -> str | None:
    for name in ("link", "a"):
        for el in soup.find_all(name):
            if not isinstance(el, Tag):
                continue
            rel = el.get("rel")
            rels = rel if isinstance(rel, list) else (str(rel).split() if rel else [])
            if any(str(r).lower() == "next" for r in rels):
                href = el.get("href")
                if href:
                    return str(href)
    return None


# ---------- content-region detection ---------- #


def detect_region(soup1: BeautifulSoup, soup2: BeautifulSoup) -> RegionPath | None:
    """Structurally locate the per-page content region by diffing page 1 vs page 2.

    Descend from `<body>` while exactly one matched-identity child differs between the two
    pages (the framing is identical, so only the content path differs); stop when several
    children differ (those are the repeating items) — that container is the content region.
    Returns its `RegionPath`, or None when the diff is ambiguous (lands on `<body>`/`<html>`
    or nothing differs) — the caller then needs a declared `content_selector`.
    """
    n1: Tag | None = soup1.body or (soup1 if isinstance(soup1, Tag) else None)
    n2: Tag | None = soup2.body or (soup2 if isinstance(soup2, Tag) else None)
    if n1 is None or n2 is None or _norm_text(n1) == _norm_text(n2):
        return None
    while True:
        pair = _single_differing_child(n1, n2)
        if pair is None:
            break
        n1, n2 = pair
    if getattr(n1, "name", None) in (None, "body", "html", "[document]"):
        return None
    return _region_path(n1)


def locate_region(soup: BeautifulSoup, region: str | RegionPath | None) -> Tag | None:
    """Resolve `region` in `soup`: a CSS selector string via `select_one`, or a `RegionPath`
    walked from `<body>` step by step. None when `region` is None or can't be located."""
    if region is None:
        return None
    if isinstance(region, str):
        el = soup.select_one(region)
        return el if isinstance(el, Tag) else None
    node: Tag | None = soup.body or (soup if isinstance(soup, Tag) else None)
    for sig, idx in region:
        if node is None:
            return None
        matches = [
            c for c in node.find_all(recursive=False) if isinstance(c, Tag) and _node_sig(c) == sig
        ]
        if idx >= len(matches):
            return None
        node = matches[idx]
    return node


def _single_differing_child(n1: Tag, n2: Tag) -> tuple[Tag, Tag] | None:
    """The single direct-child pair (by identity signature) whose text differs, or None when
    zero or more than one differ."""
    c1 = _indexed_children(n1)
    c2 = _indexed_children(n2)
    differing: list[tuple[Tag, Tag]] = []
    for key, t1 in c1.items():
        t2 = c2.get(key)
        if t2 is not None and _norm_text(t1) != _norm_text(t2):
            differing.append((t1, t2))
    return differing[0] if len(differing) == 1 else None


def _indexed_children(node: Tag) -> dict[tuple[str, int], Tag]:
    """Direct child tags keyed by (signature, occurrence-index) so same-signature siblings
    align deterministically across two pages."""
    out: dict[tuple[str, int], Tag] = {}
    counts: dict[str, int] = {}
    for c in node.find_all(recursive=False):
        if not isinstance(c, Tag):
            continue
        sig = _node_sig(c)
        idx = counts.get(sig, 0)
        counts[sig] = idx + 1
        out[(sig, idx)] = c
    return out


def _node_sig(tag: Tag) -> str:
    classes = tag.get("class") or []
    return f"{tag.name}#{tag.get('id') or ''}.{'.'.join(sorted(str(c) for c in classes))}"


def _region_path(tag: Tag) -> RegionPath:
    path: RegionPath = []
    cur: Any = tag
    while isinstance(cur, Tag) and cur.name not in (None, "body", "html", "[document]"):
        path.append(_child_index(cur))
        cur = cur.parent
    path.reverse()
    return path


def _child_index(tag: Tag) -> tuple[str, int]:
    sig = _node_sig(tag)
    idx = 0
    for sib in tag.previous_siblings:
        if isinstance(sib, Tag) and _node_sig(sib) == sig:
            idx += 1
    return sig, idx


# ---------- merge ---------- #


class RegionUnresolved(Exception):
    """No content region could be resolved (auto-detect ambiguous and none declared), so a
    lossless multi-page merge isn't possible. The caller ingests page 1 only and flags it."""


def merge_pages(
    pages_html: list[str],
    *,
    content_selector: str | list[str] | None = None,
    canonical_selector: str | list[str] | None = None,
) -> tuple[str, int]:
    """Merge `pages_html` (page 1 = framework) into one HTML; return `(merged_html, items)`.

    Region precedence: declared `content_selector` → the host's `canonical_selector` → the
    structural `detect_region` diff. Later pages' content children are appended into page 1's
    region in order, **deduped by element `id`, else by a normalized-subtree hash** (so a
    repeated quoted-OP / threaded post isn't double-counted). A later page that adds zero new
    children stops the walk (the generic terminator). `items` is the merged content-item count
    (see `_count_items` — id-bearing children, e.g. forum posts, when any are present; else all
    direct element children). Raises `RegionUnresolved` when no region resolves.
    """
    if not pages_html:
        return "", 0
    soup1 = BeautifulSoup(pages_html[0], "html.parser")

    declared = _first_selector(content_selector) or _first_selector(canonical_selector)
    locator: str | RegionPath
    if declared:
        locator = declared
        region1 = locate_region(soup1, declared)
    elif len(pages_html) >= 2:
        path = detect_region(soup1, BeautifulSoup(pages_html[1], "html.parser"))
        if path is None:
            raise RegionUnresolved("could not auto-detect a content region; declare content_selector")  # noqa: E501
        locator = path
        region1 = locate_region(soup1, path)
    else:
        region1 = None

    if region1 is None:
        raise RegionUnresolved("content region not found on page 1")

    seen: set[tuple[str, str]] = {_dedup_key(c) for c in _element_children(region1)}
    for page_html in pages_html[1:]:
        pregion = locate_region(BeautifulSoup(page_html, "html.parser"), locator)
        if pregion is None:
            log.debug("pagination: content region not found on a later page; skipping it")
            continue
        added = 0
        for child in _element_children(pregion):
            key = _dedup_key(child)
            if key in seen:
                continue
            seen.add(key)
            _promote_lazy_imgs(child)
            region1.append(child)  # moves child out of its (discarded) page soup
            added += 1
        if added == 0:
            break

    return str(soup1), _count_items(region1)


def expected_count(html: str, *, cfg: PaginationConfig) -> int | None:
    """The site-advertised item count from `cfg.expect_selector`'s text (e.g. XenForo
    "53 replies" → 53), or None when no selector is declared / no number is present."""
    if not cfg.expect_selector:
        return None
    el = BeautifulSoup(html, "html.parser").select_one(cfg.expect_selector)
    if not isinstance(el, Tag):
        return None
    m = re.search(r"\d[\d,]*", el.get_text(" ", strip=True))
    return int(m.group(0).replace(",", "")) if m else None


def _first_selector(sel: str | list[str] | None) -> str | None:
    if isinstance(sel, list):
        return str(sel[0]) if sel else None
    return str(sel) if sel else None


def _element_children(tag: Tag) -> list[Tag]:
    return [c for c in tag.find_all(recursive=False) if isinstance(c, Tag)]


def _count_items(region: Tag) -> int:
    """Count the content items in a merged region for the `posts` provenance + completeness
    check. Forum/CMS posts carry stable ids (`article id="js-post-N"`), while framework nodes
    that ride inside the content region (page-nav, "post reply" bars) typically don't — so
    count **id-bearing** direct children when any are present, else fall back to all direct
    element children (id-less repeating items). This keeps `posts` an honest item count rather
    than inflating it with framework `div`s (the g8board "56 items" vs 54 posts mismatch)."""
    children = _element_children(region)
    id_bearing = [c for c in children if c.get("id")]
    return len(id_bearing) if id_bearing else len(children)


def _dedup_key(tag: Tag) -> tuple[str, str]:
    if tag.get("id"):
        return ("id", str(tag["id"]))
    digest = hashlib.blake2b(
        (_node_sig(tag) + "|" + _norm_text(tag)).encode("utf-8"), digest_size=16
    ).hexdigest()
    return ("hash", digest)


def _promote_lazy_imgs(node: Tag) -> None:
    imgs = [node] if node.name == "img" else [i for i in node.find_all("img") if isinstance(i, Tag)]
    for img in imgs:
        if img.get("src"):
            continue
        for attr in _LAZY_SRC_ATTRS:
            if img.get(attr):
                img["src"] = img[attr]
                break


def _norm_text(tag: Tag) -> str:
    return " ".join(tag.get_text(" ", strip=True).split())
