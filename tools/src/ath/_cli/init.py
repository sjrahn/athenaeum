"""`ath init` — scaffold a new Athenaeum instance (spec Part I §2.2).

Creates, in the target directory: the instance config (`athenaeum.yaml`, from
the packaged template), the corpus skeleton (via the corpus scaffolder at
`corpus/`), the ledger skeleton (`ledger/` per spec/ledger.md §3), the persona
boot brief (`CLAUDE.md`), the agent definitions (`.claude/agents/`), and a
root `.gitignore` — so a fresh instance is self-contained for working sessions
from its first commit. Initializes a git repository unless one exists.

Idempotent per file: an existing file is never overwritten (reported and
skipped), so re-running against a partial scaffold completes it.
"""

from __future__ import annotations

import argparse
import subprocess
from collections.abc import Sequence
from importlib import resources
from pathlib import Path

from ath.manifest import MANIFEST_NAME

_LEDGER_DIRS = ("facts", "interpretations", "schemas", "harvest", "invariants", "docs")

_LEDGER_FACTS_SCHEMA = """\
# The fact model — authoring conventions

The normative contract is spec/ledger.md (§4 facts, §5 claims, §6 evidence).
This file carries this ledger's own per-type conventions — which side stores a
directed relation, value shapes for attribute claims, applicability
disciplines. Grow it as real shapes recur; shapes that harden graduate into
schemas/ (spec/ledger.md §4.4).
"""

_LEDGER_INTERP_SCHEMA = """\
# Interpretations — authoring conventions

The normative contract is spec/ledger.md §7: hypotheses, assessments,
corrections, and their needs. One interpretation per checkable statement.
"""

_OPENQ_SKELETON = """\
# Open questions

<!--worklist:begin-->
<!--worklist:end-->

## Curated
"""


def _write(path: Path, content: str, made: list[str], skipped: list[str]) -> None:
    if path.exists():
        skipped.append(str(path))
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    made.append(str(path))


def run(argv: Sequence[str]) -> int:
    ap = argparse.ArgumentParser(prog="ath init", description=__doc__)
    ap.add_argument("target", nargs="?", default=".",
                    help="target directory for the new instance (default: cwd)")
    ap.add_argument("--name", default=None,
                    help="instance display name (default: the target directory's name)")
    ns = ap.parse_args(list(argv))

    root = Path(ns.target).resolve()
    root.mkdir(parents=True, exist_ok=True)
    name = ns.name or root.name
    made: list[str] = []
    skipped: list[str] = []

    templates = resources.files("ath") / "templates"

    _write(root / MANIFEST_NAME,
           (templates / "athenaeum.yaml").read_text(encoding="utf-8")
           .replace("name: my-athenaeum", f"name: {name}"),
           made, skipped)
    _write(root / "CLAUDE.md",
           (templates / "CLAUDE.md").read_text(encoding="utf-8").replace("{name}", name),
           made, skipped)
    _write(root / ".gitignore",
           (templates / "gitignore").read_text(encoding="utf-8"),
           made, skipped)

    agents_dir = root / ".claude" / "agents"
    for entry in (templates / "agents").iterdir():
        if entry.name.endswith(".md"):
            _write(agents_dir / entry.name, entry.read_text(encoding="utf-8"),
                   made, skipped)

    # The corpus layer — the corpus scaffolder owns its shape (records/,
    # schema/ seeds, corpus-local .gitignore).
    corpus_root = root / "corpus"
    if (corpus_root / "records").is_dir():
        skipped.append(str(corpus_root))
    else:
        from corpus import scaffold

        scaffold.scaffold(corpus_root)
        made.append(str(corpus_root))
    (corpus_root / "runbooks").mkdir(parents=True, exist_ok=True)

    # The ledger layer (spec/ledger.md §3).
    ledger_root = root / "ledger"
    for d in _LEDGER_DIRS:
        (ledger_root / d).mkdir(parents=True, exist_ok=True)
    _write(ledger_root / "facts" / "SCHEMA.md", _LEDGER_FACTS_SCHEMA, made, skipped)
    _write(ledger_root / "interpretations" / "SCHEMA.md", _LEDGER_INTERP_SCHEMA,
           made, skipped)
    _write(ledger_root / "open-questions.md", _OPENQ_SKELETON, made, skipped)

    if not (root / ".git").exists():
        res = subprocess.run(["git", "init", str(root)], capture_output=True, text=True)
        if res.returncode == 0:
            made.append(str(root / ".git"))
        else:
            print(f"note: git init failed ({res.stderr.strip()}); initialize manually")

    for path in made:
        print(f"created  {path}")
    for path in skipped:
        print(f"kept     {path}")
    print(f"\ninstance ready at {root}")
    print("next: fill in athenaeum.yaml (tracker, references), then commit.")
    return 0
