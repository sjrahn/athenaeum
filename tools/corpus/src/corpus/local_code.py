"""Load a corpus's own local Python — `<corpus_root>/<subdir>/*.py` — so corpus-owned
modules can register extensions into the package's registries (capturers under
`capturers/`, drafters under `drafters/`, …).

Each file is imported **by path** (`importlib.util.spec_from_file_location`, not `sys.path`),
so distinct corpora can't collide on a shared package name and test corpora stay isolated.
Single-file modules only — relative imports between corpus-local modules aren't supported.

**Trust boundary**: this executes Python from `corpus_root`. That code is authored by the
corpus owner — the entire point of the corpus-local extension tiers — but it IS code
execution from the corpus directory.

Idempotent per `(corpus_root, subdir)`: a given dir is imported at most once per process,
marked BEFORE loading so a failing module won't retry-loop.
"""

from __future__ import annotations

import importlib.util
import logging
import sys
from pathlib import Path

log = logging.getLogger("corpus.local_code")

# (resolved corpus_root, subdir) pairs already imported this process.
_loaded: set[tuple[str, str]] = set()
_load_seq = 0


def load_corpus_modules(corpus_root: Path | None, subdir: str) -> None:
    """Import `<corpus_root>/<subdir>/*.py` (each non-`_`-prefixed file, by path) so their
    registration decorators run and populate the package registries. Idempotent per
    `(corpus_root, subdir)`; a no-op when `corpus_root` is None or the directory is absent.
    Per-file failures are logged and skipped (one bad module doesn't sink the rest)."""
    global _load_seq

    if corpus_root is None:
        return
    key = (str(Path(corpus_root).resolve()), subdir)
    if key in _loaded:
        return
    _loaded.add(key)  # mark before loading so a failure won't retry-loop

    code_dir = Path(corpus_root) / subdir
    if not code_dir.is_dir():
        return

    seq = _load_seq
    _load_seq += 1
    for py in sorted(code_dir.glob("*.py")):
        if py.stem.startswith("_"):
            continue
        modname = f"_corpus_{subdir}_{seq}_{py.stem}"
        try:
            spec = importlib.util.spec_from_file_location(modname, py)
            if spec is None or spec.loader is None:
                continue
            module = importlib.util.module_from_spec(spec)
            # Register in sys.modules BEFORE exec so machinery that resolves a class's module
            # by name works — `@dataclass` (and typing/pickle) look up `sys.modules[__module__]`,
            # which is None for a by-path module that was never registered.
            sys.modules[modname] = module
            try:
                spec.loader.exec_module(module)
            except Exception:
                sys.modules.pop(modname, None)
                raise
        except Exception as exc:  # noqa: BLE001 — one bad corpus module mustn't sink the rest
            log.warning("failed to load corpus-local %s module %s: %s", subdir, py.name, exc)
