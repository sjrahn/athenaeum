"""Rebuild a record from a decomposed working dir.

`compile` writes the record in full, so a working dir whose base has moved on rewrites the
record BACKWARD (#76). `decompose` has always stamped the source record's sha256 into the
working dir's lock; this verb now checks it, because the failure mode is a STALE BASE and not
a wrong target — in the incident that opened the ticket the destination path was correct and
the content was old, so neither a dry-run nor an `--out` would have caught it unnoticed. The
three flags here serve three different needs: `--dry-run` predicts, `--out` experiments
without putting an authored record at risk, `--ignore-base-drift` overrides deliberately.

The dry run found a second way this verb lost authored work, on its first real record — see
`recordbuild.write_workdir` for the fix. It converted a pre-3.4 roster to the members block as
a side effect, shedding the retired per-asset descriptions, which §12.26 forbids: serialization
is form-preserving precisely so that touching a record for an unrelated reason never converts
it. Conversion belongs to re-attestation, which reports what it drops.
"""

from __future__ import annotations

import argparse
import difflib
import sys
from pathlib import Path

from corpus import lint as _lint
from corpus import paths, recordbuild, records, segments, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("workdir", type=Path, help="Decomposed working dir.")
    parser.add_argument(
        "--model",
        default=None,
        help="LLM model id whose run this compile carries (records a combined touch).",
    )
    parser.add_argument(
        "--no-lint",
        action="store_true",
        help="Skip the lint gate (allow writes even when findings are present).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Write nothing; print the diff the compile would apply. The exit status "
             "predicts the real run's (so drift and lint errors still report non-zero).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Write to this path instead of the record in the corpus — for testing compile "
             "behaviour with no authored record at risk. Skips the base-drift check.",
    )
    parser.add_argument(
        "--ignore-base-drift",
        action="store_true",
        help="Overwrite even though the live record has changed since this working dir was "
             "decomposed. Deliberate clobber; the changes since are lost.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    workdir: Path = args.workdir
    dry_run: bool = args.dry_run
    out: Path | None = args.out
    rebuilt = recordbuild.read_workdir(workdir, root)

    record_id = rebuilt.metadata.get("id", "")
    target = out if out is not None else paths.record_path(root, record_id)

    # The exit status of a dry run predicts the real run's, so a refusal it foresees is
    # recorded and reported rather than returned — the diff is the thing you need to SEE
    # when your base is stale, since it is exactly what compiling would destroy.
    exit_code = 0

    # The base gate (#76). `--out` is exempt: nothing authored is at risk.
    if out is None:
        base = recordbuild.check_base(workdir, target)
        if not base.stamped:
            print(
                f"  warning: {workdir} carries no decompose stamp — the base cannot be "
                f"verified, so this write is as unguarded as it was before #76.",
                file=sys.stderr,
            )
        elif base.drift:
            print(f"  {'would refuse' if dry_run else 'REFUSING'}: {base.drift}", file=sys.stderr)
            if not args.ignore_base_drift:
                print(
                    "  re-decompose and re-apply the edits, or pass --ignore-base-drift to "
                    "overwrite deliberately.",
                    file=sys.stderr,
                )
                if not dry_run:
                    return 1
                exit_code = 1

    # A dry run reports whether the edits change anything at all, which needs the record as
    # it stands BEFORE the compile touch is appended (that touch always differs).
    pre_touch_text = records.dumps(rebuilt) if dry_run else ""

    # Append the compile touch.
    base_touch = touches.script_identifier("compile")
    touch_id = f"{base_touch}+{args.model}" if args.model else base_touch
    touches.record_touch(rebuilt, touch_id)

    # Lint gate.
    blocks = segments.iter_blocks(rebuilt.content or "")
    findings = _lint.lint(rebuilt, blocks, root)
    if findings and not args.no_lint:
        for f in findings:
            print(f"  {f.severity.upper()} {f.rule_id}: {f.message}", file=sys.stderr)
        if any(f.severity == "error" for f in findings):
            if not dry_run:
                print(
                    "compile aborted: lint errors above. Re-run with --no-lint to override.",
                    file=sys.stderr,
                )
                return 1
            print(
                "  would abort: lint errors above. Re-run with --no-lint to override.",
                file=sys.stderr,
            )
            exit_code = 1

    new_text = records.dumps(rebuilt)
    if dry_run:
        live_text = target.read_text(encoding="utf-8") if target.exists() else ""
        diff = list(
            difflib.unified_diff(
                live_text.splitlines(keepends=True),
                new_text.splitlines(keepends=True),
                fromfile=f"{target} (live)",
                tofile=f"{target} (compiled)",
            )
        )
        if not diff:
            print(f"no change: the compiled record is byte-identical to {target}")
        else:
            sys.stdout.writelines(diff)
            if not live_text:
                print(f"\nwould create {target}")
            elif live_text == pre_touch_text:
                print("\nno change beyond the compile touch — these edits are a no-op")
            else:
                adds = sum(1 for ln in diff if ln.startswith("+") and not ln.startswith("+++"))
                dels = sum(1 for ln in diff if ln.startswith("-") and not ln.startswith("---"))
                print(f"\nwould write {target} (+{adds} -{dels} lines)")
        return exit_code

    records.dump(rebuilt, target)
    print(f"compiled → {target}" + ("  (--out: the corpus record is untouched)" if out else ""))
    return exit_code
