"""Local Wikipedia knowledge base for the `concept` annotation namespace (spec §4.3.3.4).

Reads a Kiwix ZIM (full-text search + article read) entirely offline via `libzim`. libzim is
**lazy-imported inside the methods**, never at module load, so the base install + the import
guard (`import corpus.draft`) stay clean without the `wiki` extra. A clear `WikiUnavailable` is
raised when libzim or the ZIM file is absent so the CLI/API can degrade gracefully.

Concept identity — the join key by which independently-annotated records relate (§4.3.3.4):
  - `wikidata:Q<n>`  — preferred, version-stable; parsed best-effort from the article HTML.
  - `enwiki:<Title>` — a ZIM article when no QID resolves (title with spaces → underscores).
  - `local:<slug>`   — a corpus-local custom concept (see `concepts.py`), not resolved here.
"""

from __future__ import annotations

import html as _html
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from . import config

WIKIPEDIA_BASE = "https://en.wikipedia.org/wiki/"


class WikiUnavailable(RuntimeError):
    """The ZIM KB can't be opened — `libzim` missing, no ZIM path, or an unreadable file."""


@dataclass(frozen=True)
class WikiHit:
    """A search result. `id` is the canonical concept id; `path` is the ZIM resolve key."""

    id: str
    title: str
    url: str
    path: str


@dataclass(frozen=True)
class WikiArticle:
    """A resolved concept: identity ladder (`label`=title, `url`, `id`) + a short `summary`."""

    id: str
    title: str
    url: str
    qid: str | None
    summary: str
    path: str


def _title_to_url(title: str) -> str:
    return WIKIPEDIA_BASE + title.strip().replace(" ", "_")


def enwiki_id(title: str) -> str:
    """The `enwiki:<Title>` canonical id for an article title (spaces → underscores)."""
    return "enwiki:" + title.strip().replace(" ", "_")


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")
# Best-effort shapes for the Wikidata item id in a Kiwix article's HTML.
_QID_RES = (
    re.compile(r"wikidata\.org/wiki/(Q\d+)"),
    re.compile(r"Special:EntityData/(Q\d+)"),
    re.compile(r'wgWikibaseItemId"\s*:\s*"(Q\d+)"'),
    re.compile(r'"wikibase_item"\s*:\s*"(Q\d+)"'),
    re.compile(r'wikibase[-_]?item["\']?\s*[:=]\s*["\']?(Q\d+)'),
)


def _extract_qid(html_text: str) -> str | None:
    for rx in _QID_RES:
        m = rx.search(html_text)
        if m:
            return "wikidata:" + m.group(1)
    return None


def _first_paragraph(html_text: str, *, limit: int = 320) -> str:
    """The first substantive `<p>` of an article, tags stripped — the chip gloss."""
    for m in re.finditer(r"<p\b[^>]*>(.*?)</p>", html_text, flags=re.S | re.I):
        text = _WS_RE.sub(" ", _html.unescape(_TAG_RE.sub("", m.group(1)))).strip()
        if len(text) >= 24:  # skip empty / boilerplate paragraphs
            return text[:limit].rstrip()
    text = _WS_RE.sub(" ", _html.unescape(_TAG_RE.sub("", html_text))).strip()
    return text[:limit].rstrip()


class WikiKB:
    """A read-only handle on a local Wikipedia ZIM. The Archive is opened lazily on first use."""

    def __init__(self, zim_path: Path):
        self.zim_path = Path(zim_path)
        self._archive: Any = None

    @property
    def archive(self) -> Any:
        if self._archive is None:
            try:
                from libzim.reader import Archive  # lazy — never imported at module load
            except ImportError as exc:
                raise WikiUnavailable(
                    "the `wiki` extra is not installed (`uv sync --extra wiki`)."
                ) from exc
            if not self.zim_path.is_file():
                raise WikiUnavailable(f"ZIM file not found: {self.zim_path}")
            try:
                self._archive = Archive(str(self.zim_path))
            except Exception as exc:  # libzim raises its own native error types
                raise WikiUnavailable(f"could not open ZIM {self.zim_path}: {exc}") from exc
        return self._archive

    # ---- resolution ----
    def _entry(self, ref: str) -> Any | None:
        """Resolve a ref (ZIM path, `enwiki:<Title>`, or a bare title) to a non-redirect entry."""
        archive = self.archive
        ref = (ref or "").strip()
        if not ref:
            return None
        if ref.startswith("enwiki:"):
            title = ref[len("enwiki:") :].replace("_", " ")
            candidates: list[tuple[str, str]] = [("title", title)]
        elif ":" in ref and ref.split(":", 1)[0] in ("wikidata", "local"):
            return None  # not resolvable against the ZIM alone
        else:
            candidates = [("path", ref), ("title", ref), ("title", ref.replace("_", " "))]
        for kind, val in candidates:
            try:
                if kind == "path" and archive.has_entry_by_path(val):
                    entry = archive.get_entry_by_path(val)
                elif kind == "title" and archive.has_entry_by_title(val):
                    entry = archive.get_entry_by_title(val)
                else:
                    continue
            except Exception:
                continue
            try:
                if entry.is_redirect:
                    entry = entry.get_redirect_entry()
            except Exception:
                pass
            return entry
        return None

    @staticmethod
    def _read_html(entry: Any) -> str:
        return bytes(entry.get_item().content).decode("utf-8", "replace")

    def _hit_from_path(self, path: str) -> WikiHit | None:
        try:
            entry = self.archive.get_entry_by_path(path)
            if entry.is_redirect:
                entry = entry.get_redirect_entry()
            title = entry.title or path
            return WikiHit(
                id=enwiki_id(title), title=title, url=_title_to_url(title), path=entry.path
            )
        except Exception:
            return None

    # ---- public API ----
    def search(self, query: str, *, limit: int = 10) -> list[WikiHit]:
        """Full-text search (falls back to / supplements with title suggestion)."""
        archive = self.archive
        q = (query or "").strip()
        if not q:
            return []
        paths: list[str] = []
        try:
            if archive.has_fulltext_index:
                from libzim.search import Query, Searcher

                res = Searcher(archive).search(Query().set_query(q))
                paths = list(res.getResults(0, limit))
        except Exception:
            paths = []
        if len(paths) < limit:
            try:
                from libzim.suggestion import SuggestionSearcher

                for p in SuggestionSearcher(archive).suggest(q).getResults(0, limit):
                    if p not in paths:
                        paths.append(p)
                    if len(paths) >= limit:
                        break
            except Exception:
                pass
        hits: list[WikiHit] = []
        for p in paths[:limit]:
            hit = self._hit_from_path(p)
            if hit is not None:
                hits.append(hit)
        return hits

    def get(self, ref: str) -> WikiArticle | None:
        """Resolve a ref to a `WikiArticle` (title, url, best-effort qid, summary)."""
        entry = self._entry(ref)
        if entry is None:
            return None
        html_text = self._read_html(entry)
        title = entry.title or entry.path
        qid = _extract_qid(html_text)
        return WikiArticle(
            id=qid or enwiki_id(title),
            title=title,
            url=_title_to_url(title),
            qid=qid,
            summary=_first_paragraph(html_text),
            path=entry.path,
        )

    def read(self, ref: str) -> str | None:
        """The full article HTML for a ref, or None when it can't be resolved."""
        entry = self._entry(ref)
        return None if entry is None else self._read_html(entry)


def zim_path_for(
    *, zim: str | os.PathLike[str] | None = None, corpus_root: Path | None = None
) -> Path | None:
    """Resolve the ZIM path: explicit arg > `ATH_WIKI_ZIM` env > `[corpus.wiki].zim`."""
    if zim:
        return Path(zim)
    env = os.environ.get("ATH_WIKI_ZIM")
    if env:
        return Path(env)
    if corpus_root is not None:
        z = config.load_config(Path(corpus_root)).wiki.get("zim")
        if z:
            return Path(z)
    return None


@lru_cache(maxsize=8)
def _kb_cached(zim_path: str) -> WikiKB:
    return WikiKB(Path(zim_path))


def open_kb(
    *, zim: str | os.PathLike[str] | None = None, corpus_root: Path | None = None
) -> WikiKB:
    """Return a (cached) `WikiKB`. Raises `WikiUnavailable` when no ZIM path can be resolved.

    The Archive itself opens lazily, so a missing libzim / ZIM file surfaces on first query.
    """
    path = zim_path_for(zim=zim, corpus_root=corpus_root)
    if path is None:
        raise WikiUnavailable(
            "no Wikipedia ZIM configured — set ATH_WIKI_ZIM, pass --zim, or add "
            "[corpus.wiki] zim to corpus.toml."
        )
    return _kb_cached(str(path))
