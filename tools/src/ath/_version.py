"""The specification version this tooling implements (`spec/CHANGELOG.md`).

One declared value, one home — deliberately dependency-free (no FastAPI, no
`ath.serve`) so any module can read it without pulling in the `serve` extra.
Bumped together with the specification version; two consumers stamp it: the
read surface's OpenAPI document (`ath.serve.app`, spec/athenaeum.md §5.1) and
the export projection's reproducibility tuple (`ledger.export`, spec/
ledger.md §15.7) — both import it from here rather than either owning it for
the other.
"""

from __future__ import annotations

SPEC_VERSION = 43
