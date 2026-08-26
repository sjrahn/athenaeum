"""Read-only validation of a decomposed working dir or a single manifest fragment.

`corpus validate-fragment <path>` parses and lints WITHOUT writing the record or recording a
touch — the worker-safe check a section-worker runs on its own fragment before returning. A
worker is forbidden `compile` precisely because compile writes the record (and, on the final
pass, records the touch); this gives back the validation without the write.

Two shapes, by what `<path>` is:

- a **directory** (a decomposed working dir): validates the fully-assembled record, resolving
  any `include`d fragments — the same read `compile` does, minus the write. Runs the full lint
  rule set.
- a **`.corpus` fragment file** (e.g. `fragments/0005-....corpus`, from `decompose --split`):
  validates just that fragment's ops in isolation — manifest grammar, body⟺lossless, and the
  segment/section/body rules meaningful without the rest of the record
  (`lint.FRAGMENT_RULES`). Record-scope rules (frontmatter, the members roster, origins,
  artifact-backed checks) are out of scope for a lone fragment — run the whole-dir form (or
  `corpus compile --dry-run`) for those.

Exit codes: 0 — no error-severity findings; 1 — at least one; 2 — invocation failure (bad
path, or a manifest parse error, surfaced with file + line).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "path",
        help="a decomposed working dir, OR a fragments/*.corpus fragment file",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit findings as newline-delimited JSON instead of grouped text",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    from corpus import lint as _lint
    from corpus import recordbuild, segments

    target = Path(args.path)
    if not target.exists():
        print(f"validate-fragment: no such path: {target}", file=sys.stderr)
        return 2

    root = resolved_corpus_root(args)

    if target.is_dir():
        scope, rules = "record", None
        try:
            post = recordbuild.read_workdir(target, root)
        except ValueError as e:  # ManifestError carries file+line+raw
            print(f"validate-fragment: {e}", file=sys.stderr)
            return 2
    else:
        scope, rules = "fragment", _lint.FRAGMENT_RULES
        try:
            post = recordbuild.read_fragment(target, root)
        except ValueError as e:
            print(f"validate-fragment: {e}", file=sys.stderr)
            return 2

    blocks = segments.iter_blocks(post.content or "")
    findings = _lint.lint(post, blocks, root, rules=rules)

    if args.json:
        import dataclasses
        import json

        for f in findings:
            sys.stdout.write(json.dumps(dataclasses.asdict(f), ensure_ascii=False) + "\n")
    else:
        _emit_text(target, scope, findings)

    return 1 if any(f.severity == "error" for f in findings) else 0


def _emit_text(target: Path, scope: str, findings: list) -> None:
    print(f"{target}  ({scope}-scope validation)")
    print()
    if not findings:
        print("no findings.")
        return
    by_sev: dict[str, list] = {"error": [], "warning": [], "info": []}
    for f in findings:
        by_sev.setdefault(f.severity, []).append(f)
    for sev, label in (("error", "errors"), ("warning", "warnings"), ("info", "infos")):
        bucket = by_sev.get(sev) or []
        if not bucket:
            continue
        print(f"{label} ({len(bucket)}):")
        for f in bucket:
            loc = f" [{f.address}]" if f.address else ""
            print(f"  {sev.upper()} {f.rule_id}{loc}: {f.message}")
        print()
