"""API-level multi-corpus config — maps corpus *ids* to on-disk roots.

The corpus tooling is single-root per invocation; fronting several corpora from one
server is purely an API concern, so it lives here. Sources, in precedence order:

1. CLI:  ``corpus-api serve --corpus <id>=<path> [--corpus <id>=<path> ...]``
2. env:  ``ATH_API_CORPORA="public=/abs/path scratch=/abs/path"`` (space/comma sep)
3. fallback: the corpus root discovered by walking up from cwd (single corpus, id from
   the directory name).

Each entry's own ``corpus.toml`` is still consulted by the library (`config.load_config`)
for the store backend / transcription adapter — this config only does id->root routing.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Per-corpus accent colors, assigned by position — mirrors the design's corpus dots
# (amber / green / violet / slate / ochre / plum). Purely cosmetic.
_PALETTE = ["#a35a00", "#4a6b3a", "#6a5a8a", "#4a6b8a", "#8a6a3a", "#7a4a8a"]


class ConfigError(ValueError):
    """A corpus spec was malformed or its root is not a corpus."""


@dataclass(frozen=True)
class CorpusEntry:
    id: str
    root: Path
    name: str
    color: str
    desc: str


@dataclass
class ApiConfig:
    corpora: list[CorpusEntry]
    # Shared local Wikipedia ZIM for the concept KB (corpus.wiki). One ZIM fronts every
    # corpus; absent → the wiki endpoints return 503 and concept chips carry no live gloss.
    wiki_zim: str | None = None

    def by_id(self, corpus_id: str) -> CorpusEntry | None:
        return next((c for c in self.corpora if c.id == corpus_id), None)


def _is_corpus_root(root: Path) -> bool:
    """A corpus root carries a ``records/`` tree (schema/ is optional but typical)."""
    return (root / "records").is_dir()


def _desc_for(root: Path) -> str:
    """First meaningful line of the corpus README, else a generic blurb."""
    readme = root / "README.md"
    if readme.is_file():
        try:
            for raw in readme.read_text("utf-8").splitlines():
                line = raw.strip().lstrip("#").strip()
                if line and not line.startswith(("![", "[!", "<!")):
                    return line[:140]
        except OSError:
            pass
    return f"Corpus at {root.name}."


def _entry(corpus_id: str, root: Path, index: int) -> CorpusEntry:
    root = root.expanduser().resolve()
    if not _is_corpus_root(root):
        raise ConfigError(f"{root} is not a corpus root (no records/ directory)")
    return CorpusEntry(
        id=corpus_id,
        root=root,
        name=corpus_id,
        color=_PALETTE[index % len(_PALETTE)],
        desc=_desc_for(root),
    )


def _parse_specs(specs: list[str]) -> list[CorpusEntry]:
    """Parse ``id=path`` (or bare ``path``, id from the dir name) specs into entries."""
    entries: list[CorpusEntry] = []
    for i, spec in enumerate(specs):
        spec = spec.strip()
        if not spec:
            continue
        if "=" in spec:
            corpus_id, _, path = spec.partition("=")
            corpus_id = corpus_id.strip()
        else:
            path = spec
            corpus_id = Path(path).expanduser().resolve().name
        if not corpus_id:
            raise ConfigError(f"empty corpus id in spec {spec!r}")
        entries.append(_entry(corpus_id, Path(path.strip()), i))
    return entries


def load_config(specs: list[str] | None = None) -> ApiConfig:
    """Resolve the served corpora from CLI specs, then env, then cwd discovery.

    The shared concept-KB ZIM defaults from `ATH_WIKI_ZIM` (a `--wiki-zim` flag may override
    it on the served config)."""
    wiki_zim = os.environ.get("ATH_WIKI_ZIM") or None

    if specs:
        return ApiConfig(_parse_specs(specs), wiki_zim=wiki_zim)

    env = os.environ.get("ATH_API_CORPORA", "").strip()
    if env:
        raw = [s for s in env.replace(",", " ").split() if s]
        return ApiConfig(_parse_specs(raw), wiki_zim=wiki_zim)

    from corpus.paths import find_corpus_root

    root = find_corpus_root()
    return ApiConfig([_entry(root.name, root, 0)], wiki_zim=wiki_zim)
