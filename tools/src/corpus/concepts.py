"""Corpus-local custom concepts + the unified concept resolver (spec §4.3.3.4).

Concepts come from two sources, layered the same way schemas are (corpus-local first):

  - **Wikipedia** — the local ZIM KB (`corpus.wiki`), keyed `wikidata:Q…` / `enwiki:<Title>`.
  - **Corpus-local** — entities that are not in Wikipedia (an internal project, a niche term, a
    private person), declared as data (not schema) under `<corpus-root>/concepts/*.yaml` and keyed
    `local:<slug>`. This mirrors custom overlays: a curatorial extension point owned by the corpus.

`ConceptResolver` spans both so a corpus-local concept resolves and renders exactly like a
Wikipedia one. Everything here is pure-Python + YAML; the KB is optional (a resolver with no KB
still resolves local concepts and degrades gracefully on Wikipedia ids).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

from .wiki import WikiKB, WikiUnavailable


@dataclass(frozen=True)
class LocalConcept:
    """A corpus-local concept declared under `<corpus-root>/concepts/`."""

    id: str  # canonical id, always `local:<slug>`
    label: str
    aliases: tuple[str, ...] = ()
    description: str | None = None
    url: str | None = None
    same_as: str | None = None  # an optional `wikidata:Q…` cross-link


@dataclass(frozen=True)
class ConceptHit:
    """A concept search result, unified across Wikipedia + corpus-local sources."""

    id: str
    label: str
    url: str | None
    source: str  # "wikipedia" | "local"


@dataclass(frozen=True)
class ResolvedConcept:
    """A fully-resolved concept — the identity ladder + a gloss for display."""

    id: str
    label: str
    url: str | None
    summary: str | None
    qid: str | None
    source: str  # "wikipedia" | "local"


def _slug_of(concept_id: str, fallback: str) -> str:
    cid = (concept_id or "").strip()
    if cid.startswith("local:"):
        return cid[len("local:") :]
    return cid or fallback


def _parse_concept_doc(doc: Any, stem: str) -> LocalConcept | None:
    if not isinstance(doc, dict):
        return None
    label = str(doc.get("label") or "").strip()
    if not label:
        return None
    slug = _slug_of(str(doc.get("id") or ""), stem)
    aliases = tuple(str(a).strip() for a in (doc.get("aliases") or []) if str(a).strip())
    desc = doc.get("description")
    return LocalConcept(
        id=f"local:{slug}",
        label=label,
        aliases=aliases,
        description=str(desc).strip() if desc else None,
        url=(str(doc.get("url")).strip() or None) if doc.get("url") else None,
        same_as=(str(doc.get("same_as")).strip() or None) if doc.get("same_as") else None,
    )


@lru_cache(maxsize=32)
def _load_local(corpus_root_str: str) -> dict[str, LocalConcept]:
    root = Path(corpus_root_str) / "concepts"
    out: dict[str, LocalConcept] = {}
    if not root.is_dir():
        return out
    for path in sorted(root.glob("*.yaml")) + sorted(root.glob("*.yml")):
        try:
            loaded = yaml.safe_load(path.read_text("utf-8"))
        except (yaml.YAMLError, OSError, UnicodeDecodeError):
            continue
        # A file may be one concept (mapping), an explicit list, or `{concepts: [...]}`.
        docs: list[Any]
        if isinstance(loaded, list):
            docs = loaded
        elif isinstance(loaded, dict) and isinstance(loaded.get("concepts"), list):
            docs = loaded["concepts"]
        else:
            docs = [loaded]
        for doc in docs:
            concept = _parse_concept_doc(doc, path.stem)
            if concept is not None:
                out[concept.id] = concept
    return out


def load_local_concepts(corpus_root: Path) -> dict[str, LocalConcept]:
    """Return `{local:<slug>: LocalConcept}` for the corpus (cached)."""
    return dict(_load_local(str(corpus_root)))


def resolve_local(corpus_root: Path, concept_id: str) -> LocalConcept | None:
    return _load_local(str(corpus_root)).get(concept_id)


def clear_cache() -> None:
    """Drop the local-concept cache (after editing the registry)."""
    _load_local.cache_clear()


def _search_local(corpus_root: Path, query: str, limit: int) -> list[ConceptHit]:
    q = (query or "").strip().lower()
    if not q:
        return []
    scored: list[tuple[int, ConceptHit]] = []
    for concept in _load_local(str(corpus_root)).values():
        names = [concept.label, *concept.aliases]
        best = None
        for name in names:
            low = name.lower()
            if low == q:
                best = 0
            elif low.startswith(q):
                best = min(1, best) if best is not None else 1
            elif q in low:
                best = min(2, best) if best is not None else 2
        if best is not None:
            scored.append(
                (best, ConceptHit(concept.id, concept.label, concept.url, "local"))
            )
    scored.sort(key=lambda t: (t[0], t[1].label.lower()))
    return [hit for _, hit in scored[:limit]]


@dataclass
class ConceptResolver:
    """Resolve + search concepts across the corpus-local registry and the Wikipedia KB.

    `kb` is optional: with no KB, local concepts still resolve and Wikipedia ids return None.
    Corpus-local hits are surfaced **first** (the source-fallback spirit of schema loading).
    """

    corpus_root: Path
    kb: WikiKB | None = None
    _seen: set[str] = field(default_factory=set, repr=False)

    def search(self, query: str, *, limit: int = 10) -> list[ConceptHit]:
        hits: list[ConceptHit] = list(_search_local(self.corpus_root, query, limit))
        seen = {h.id for h in hits}
        if self.kb is not None and len(hits) < limit:
            try:
                for wh in self.kb.search(query, limit=limit):
                    if wh.id in seen:
                        continue
                    hits.append(ConceptHit(wh.id, wh.title, wh.url, "wikipedia"))
                    seen.add(wh.id)
                    if len(hits) >= limit:
                        break
            except WikiUnavailable:
                pass
        return hits[:limit]

    def get(self, concept_id: str) -> ResolvedConcept | None:
        cid = (concept_id or "").strip()
        if not cid:
            return None
        if cid.startswith("local:"):
            concept = resolve_local(self.corpus_root, cid)
            if concept is None:
                return None
            qid = concept.same_as if (concept.same_as or "").startswith("wikidata:") else None
            return ResolvedConcept(
                id=concept.id,
                label=concept.label,
                url=concept.url,
                summary=concept.description,
                qid=qid,
                source="local",
            )
        if self.kb is not None:
            try:
                art = self.kb.get(cid)
            except WikiUnavailable:
                return None
            if art is not None:
                return ResolvedConcept(
                    id=art.id,
                    label=art.title,
                    url=art.url,
                    summary=art.summary,
                    qid=art.qid,
                    source="wikipedia",
                )
        return None
