"""The specification version this tooling implements (`spec/CHANGELOG.md`).

One declared value, one home — deliberately dependency-free (no FastAPI, no
`ath.serve`) so any module can read it without pulling in the `serve` extra.
Bumped together with the specification version; two consumers stamp it: the
read surface's OpenAPI document (`ath.serve.app`, spec/athenaeum.md §5.1) and
the export projection's reproducibility tuple (`ledger.export`, spec/
ledger.md §15.7) — both import it from here rather than either owning it for
the other.

A string, because the v47 maintenance line carries a maintenance-line label
(`47.1`, owner ruling 2026-10-28) where the unified line carries an integer:
the unified line already holds v48 through v52, so a maintenance amendment is labelled
on its own line and renumbered into the unified one at migration.
"""

from __future__ import annotations

SPEC_VERSION = "47.1"
