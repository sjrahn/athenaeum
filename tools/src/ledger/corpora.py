"""The corpus join — bare-hash resolution across the registered corpora.

Evidence cites `corpus://{hash}` with no corpus qualifier (§6.2): a hash
either resolves in some registered corpus or it doesn't. Which corpora hold
the bytes drives derived sensitivity (§6.4); the record's `status` drives the
normalized-citation discipline (§6.3). Everything here is read-only stat/head
access against `records/{ab}/{hash}.md` — no corpus tooling is invoked.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

_STATUS_RANK = {"stub": 0, "draft": 1, "normalized": 2}


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
        self._status: dict[str, tuple[str | None, str]] = {}  # hash -> (status, touch)

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

    def status(self, hash_: str) -> str | None:
        """The best lifecycle status across holders (normalized > draft > stub)."""
        return self._meta(hash_)[0]

    def touch(self, hash_: str) -> str:
        """The latest touch identity of the best-status holder ("" when none)."""
        return self._meta(hash_)[1]

    def _meta(self, hash_: str) -> tuple[str | None, str]:
        if hash_ not in self._status:
            best: str | None = None
            best_touch = ""
            for c in self.holders(hash_):
                fm = _read_frontmatter(self.record_path(c.root, hash_))
                st = fm.get("status")
                if isinstance(st, str) and (
                    best is None or _STATUS_RANK.get(st, -1) > _STATUS_RANK.get(best, -1)
                ):
                    best = st
                    touches = fm.get("touch") or []
                    best_touch = str(touches[-1]) if isinstance(touches, list) and touches else ""
            self._status[hash_] = (best, best_touch)
        return self._status[hash_]
