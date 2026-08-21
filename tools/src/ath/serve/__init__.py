"""`ath serve` — the read surface (spec/athenaeum.md §5.1).

A read-only HTTP surface over an instance's corpus + ledger join, serving the
same contracts the distribution's other consumers get (`ledger.scope`,
`ledger.demands`, the corpus resolver, the refdata adapters) over a
transport. Framework types (FastAPI, Starlette) stay inside this package —
`create_app` is the one thing anything outside `ath.serve` imports.
"""

from __future__ import annotations

from ath.serve.app import SPEC_VERSION, create_app

__all__ = ["SPEC_VERSION", "create_app"]
