"""Run the conformance linter against a record (or all records in the corpus)."""

from __future__ import annotations

import argparse
import dataclasses
import json
import sys

from corpus import lint as _lint
from corpus import paths, records, segments
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "target",
        nargs="?",
        default=None,
        help=(
            "Hash, hex prefix, or record file path. If omitted, lints every "
            "record in the corpus."
        ),
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="emit findings as a single JSON array (each: the Finding fields + record_id) — "
        "the normalizer maps these to issues.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    if args.target is None:
        return _lint_all(root, json_out=args.json)
    record_id, record_file = paths.resolve_record(root, args.target)
    return _lint_one(root, record_id, record_file, json_out=args.json)


def _payloads(record_id: str, findings) -> list[dict]:
    """`asdict(Finding)` + `record_id`, one dict per finding."""
    return [{**dataclasses.asdict(f), "record_id": record_id} for f in findings]


def _dump_json(payloads: list[dict]) -> None:
    """Emit a single JSON array (not NDJSON) so a consumer can `json.load` the whole stream."""
    sys.stdout.write(json.dumps(payloads, ensure_ascii=False, indent=2) + "\n")


def _lint_one(root, record_id, record_file, *, json_out: bool = False) -> int:
    post = records.load(record_file)
    blocks = segments.iter_blocks(post.content or "")
    findings = _lint.lint(post, blocks, root)
    if json_out:
        _dump_json(_payloads(record_id, findings))
        return 1 if any(f.severity == "error" for f in findings) else 0
    if not findings:
        print(f"{record_id}: clean")
        return 0
    err = 0
    for f in findings:
        if f.severity == "error":
            err += 1
        loc = f" [{f.address}]" if f.address else ""
        print(f"{record_id}: {f.severity.upper()} {f.rule_id}{loc}: {f.message}")
    return 1 if err else 0


def _lint_all(root, *, json_out: bool = False) -> int:
    records_dir = root / "records"
    if not records_dir.is_dir():
        print("no records/ dir")
        return 0
    any_err = 0
    any_record = False
    all_payloads: list[dict] = []
    for md in records.iter_record_paths(root):
        any_record = True
        try:
            post = records.load(md)
            blocks = segments.iter_blocks(post.content or "")
            findings = _lint.lint(post, blocks, root)
        except Exception as e:
            print(f"{md.stem}: ERROR loading: {e}", file=sys.stderr)
            any_err = 1
            continue
        if json_out:
            all_payloads.extend(_payloads(md.stem, findings))
            if any(f.severity == "error" for f in findings):
                any_err = 1
            continue
        for f in findings:
            if f.severity == "error":
                any_err = 1
            loc = f" [{f.address}]" if f.address else ""
            print(f"{md.stem}: {f.severity.upper()} {f.rule_id}{loc}: {f.message}")
    if json_out:
        _dump_json(all_payloads)  # one array across all records (empty array if none)
    elif not any_record:
        print("no records to lint")
    return any_err
