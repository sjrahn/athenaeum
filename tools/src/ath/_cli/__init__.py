"""`ath` — the Athenaeum umbrella CLI.

A thin, lazy dispatcher: system-level verbs (`sync`, `status`) plus the
delegation shim (`ath corpus …` → the corpus CLI, verbatim). Mirrors the
corpus dispatcher's lazy-import discipline so the base import path stays
clean; there is deliberately no bare `ledger` command. (v15: the codex verbs
left with the codex kit — the system's distribution carries no consumer
tooling.)
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

_USAGE = """\
usage: ath <command> [options...]

Athenaeum system tooling — drive the members from the orchestrator repo.

System:
  status        working-tree state of the orchestrator repo and every member
  sync          clone missing members; fetch + report the rest (--pull to fast-forward)
  issue ...     the system's backlog: list, show, sync (the in-repo offline snapshot).
                Write verbs — create, close and above all COMMENT — are `fj`'s.

Layers:
  ledger ...    the ledger's deterministic surface: check, verify, harvest,
                promote, stamp, worklist, regen (spec/ledger.md)
  ref ...       the reference-dataset resolver: status, resolve, search,
                index, hash (spec/ledger.md §6.5)

Delegation:
  corpus ...    the corpus CLI, verbatim (equivalent to running `corpus ...`)

The manifest (athenaeum.yaml) is located by walking up from the current
directory; pass --root to a system verb to point elsewhere.
"""


def main(argv: Sequence[str] | None = None) -> int:
    """Console-script entry point."""
    args = list(sys.argv[1:] if argv is None else argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_USAGE, end="")
        return 0
    cmd, rest = args[0], args[1:]
    if cmd == "corpus":
        from corpus._cli import main as corpus_main

        return corpus_main(rest)
    if cmd == "ledger":
        from ledger._cli import main as ledger_main

        return ledger_main(rest)
    if cmd == "ref":
        from ath._cli.ref import run as ref_run

        return ref_run(rest)
    if cmd == "sync":
        from ath._cli.sync import run

        return run(rest)
    if cmd == "status":
        from ath._cli.status import run

        return run(rest)
    if cmd == "issue":
        from ath._cli.issue import run

        return run(rest)
    print(f"ath: unknown command {cmd!r}", file=sys.stderr)
    print("Run 'ath --help' to see available commands.", file=sys.stderr)
    return 2
