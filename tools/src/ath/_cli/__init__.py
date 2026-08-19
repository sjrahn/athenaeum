"""`ath` — the Athenaeum instance umbrella CLI.

A thin, lazy dispatcher: instance verbs (`init`, `status`, `issue`) plus the
layer surfaces (`ledger`, `ref`) and the delegation shim (`ath corpus …` →
the corpus CLI, verbatim). Mirrors the corpus dispatcher's lazy-import
discipline so the base import path stays clean; there is deliberately no bare
`ledger` command, and the distribution carries no consumer tooling.
"""

from __future__ import annotations

import sys
from collections.abc import Sequence

_USAGE = """\
usage: ath <command> [options...]

Athenaeum tooling — point at an instance and work inside it (spec Part I §2).

Instance:
  init [PATH]   scaffold a new instance: config, corpus + ledger skeletons,
                persona brief, agent definitions
  status        instance working-tree state and config summary
  issue ...     the instance's backlog: list, show, sync (the in-repo offline
                snapshot). Write verbs — create, close and above all COMMENT —
                are the forge CLI's (`fj`).

Layers:
  ledger ...    the ledger's deterministic surface: check, verify, harvest,
                promote, stamp, worklist, regen (spec/ledger.md)
  ref ...       the reference-dataset resolver: status, resolve, search,
                index, hash (spec/ledger.md §6.5)

Delegation:
  corpus ...    the corpus CLI, verbatim (equivalent to running `corpus ...`)

The instance is located by walking up from the current directory for
athenaeum.yaml ($ATHENAEUM_ROOT overrides); pass --root to a verb to point
elsewhere.
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
    if cmd == "init":
        from ath._cli.init import run as init_run

        return init_run(rest)
    if cmd == "status":
        from ath._cli.status import run

        return run(rest)
    if cmd == "issue":
        from ath._cli.issue import run

        return run(rest)
    print(f"ath: unknown command {cmd!r}", file=sys.stderr)
    print("Run 'ath --help' to see available commands.", file=sys.stderr)
    return 2
