"""The corpus join — bare-hash resolution across the registered corpora.

Evidence cites `corpus://{hash}` with no corpus qualifier (§6.2): a hash
either resolves in some registered corpus or it doesn't. Which corpora hold
the bytes drives derived sensitivity (§6.4); citability keys to verifiable
surfaces, never to a stored lifecycle field (§6.3) — the corpus `status`
frontmatter key is retired (`spec/corpus.md` §4.1) and this module reads none
of it. Everything here is read-only stat/head access against
`records/{ab}/{hash}.md` — no corpus tooling is invoked, with one deliberate
exception: the *(1.8)* deferred-surface predicate asks `corpus.mime` for the
record's declared citation-surface class (a pure schema-first lookup — ledger
depends on corpus, so this is a library call, never a re-implementation).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

_ARTIFACT_OPENER_RE = re.compile(r"(?m)^<!--artifact ([\w.+-]+/[\w.+-]+)")
_SEGMENT_OPENER_RE = re.compile(r"(?m)^<!--segment ")


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
        self._deferred: dict[str, bool | None] = {}
        self._tenancy_private: dict[str, bool] = {}

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
        """§6.4 *(1.9)*: private iff no holding record's TENANCY is public; None =
        unresolved. Tenancy derives per record — origin-overlay `tenancy:`
        declarations and `corpus://` lineage inheritance, falling closed to the
        holding corpus's manifest `visibility:` when nothing declares
        (`ledger.tenancy.record_tenancy`). Any-public-wins across holders, which
        preserves the same-bytes rule the corpus-membership lookup enforced:
        bytes public anywhere are public evidence."""
        held = self.holders(hash_)
        if not held:
            return None
        if hash_ not in self._tenancy_private:
            from ledger.tenancy import record_tenancy

            self._tenancy_private[hash_] = not any(
                record_tenancy(c.root, hash_,
                               default=("private" if c.private else "public")) == "public"
                for c in held
            )
        return self._tenancy_private[hash_]

    def deferred_surface(self, hash_: str) -> bool | None:
        """*(1.8, §5.4/§13.2.4)* True when the record's citable surface is DEFERRED —
        its mime declares `citation_surface: segments` (corpus §7.1) and the record
        persists no segments yet — so its evidence is admissible but excluded from
        the authentication bar until the declared surface lands. False for every
        verifiable surface; None when the hash does not resolve. Read from the same
        holder `touch()` reads (manifest order), on the same tolerant terms: an
        unreadable record answers False, never an error — surface state is a grading
        input, and grading must not invent failures resolution didn't find."""
        if hash_ not in self._deferred:
            state: bool | None = None
            holders = self.holders(hash_)
            if holders:
                state = False
                try:
                    text = self.record_path(holders[0].root, hash_).read_text(
                        encoding="utf-8", errors="replace")
                except OSError:
                    text = ""
                m = _ARTIFACT_OPENER_RE.search(text)
                if m and not _SEGMENT_OPENER_RE.search(text):
                    from corpus.mime import citation_surface  # deferred: heavy package

                    state = citation_surface(m.group(1),
                                             corpus_root=holders[0].root) == "segments"
            self._deferred[hash_] = state
        return self._deferred[hash_]

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
