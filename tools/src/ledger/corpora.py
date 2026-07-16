"""The corpus join — bare-hash resolution across the registered corpora.

Evidence cites `corpus://{hash}` with no corpus qualifier (§6.2): a hash
either resolves in some registered corpus or it doesn't. Which corpora hold
the bytes drives derived sensitivity (§6.4); citability keys to verifiable
surfaces, never to a stored lifecycle field (§6.3) — the corpus `status`
frontmatter key is retired (`spec/corpus.md` §4.1) and this module reads none
of it. Everything here is read-only stat/head access against
`records/{ab}/{hash}.md` — no corpus tooling is invoked.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class RegisteredCorpus:
    name: str
    root: Path
    private: bool

    @property
    def available(self) -> bool:
        return (self.root / "records").is_dir()


def _read_frontmatter(path: Path) -> dict:
    """The YAML frontmatter of a record, or {} — tolerant by contract."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return {}
    if not text.startswith("---"):
        return {}
    end = text.find("\n---", 3)
    if end == -1:
        return {}
    try:
        data = yaml.safe_load(text[3:end])
    except yaml.YAMLError:
        return {}
    return data if isinstance(data, dict) else {}


class CorpusJoin:
    """Lazy hash → holding-corpora resolution with per-hash caching."""

    def __init__(self, corpora: list[RegisteredCorpus]):
        self.corpora = corpora
        self._holders: dict[str, list[RegisteredCorpus]] = {}
        self._touch: dict[str, str] = {}

    @property
    def complete(self) -> bool:
        """True when every registered corpus is present on disk."""
        return all(c.available for c in self.corpora)

    @property
    def missing(self) -> list[str]:
        return [c.name for c in self.corpora if not c.available]

    @staticmethod
    def record_path(root: Path, hash_: str) -> Path:
        return root / "records" / hash_[:2] / f"{hash_}.md"

    def holders(self, hash_: str) -> list[RegisteredCorpus]:
        if hash_ not in self._holders:
            self._holders[hash_] = [
                c for c in self.corpora if self.record_path(c.root, hash_).is_file()
            ]
        return self._holders[hash_]

    def resolves(self, hash_: str) -> bool:
        return bool(self.holders(hash_))

    def is_private(self, hash_: str) -> bool | None:
        """§6.4: private iff the hash resolves ONLY in private corpora; None = unresolved."""
        held = self.holders(hash_)
        if not held:
            return None
        return all(c.private for c in held)

    def touch(self, hash_: str) -> str:
        """The latest touch identity of the record ("" when none). Read from
        the first holding corpus's copy — the same holder `verify` parses for
        content (`load_record_content`), so the stamp and the staleness compare
        see one consistent chain. (Multi-holder hashes have INDEPENDENT record
        files and touch chains; holder selection is stable — manifest order.)"""
        if hash_ not in self._touch:
            touch = ""
            holders = self.holders(hash_)
            if holders:
                fm = _read_frontmatter(self.record_path(holders[0].root, hash_))
                touches = fm.get("touch") or []
                touch = str(touches[-1]) if isinstance(touches, list) and touches else ""
            self._touch[hash_] = touch
        return self._touch[hash_]
