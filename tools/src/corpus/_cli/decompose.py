"""Decompose a record into a working dir (manifest + body/desc sidecars)."""

from __future__ import annotations

import argparse
from pathlib import Path

from corpus import paths, recordbuild, records, segments
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "--into",
        type=Path,
        default=None,
        help="Output directory (default: /tmp/<id[:12]>/).",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    record_id, record_file = paths.resolve_record(root, args.target)
    out_dir = args.into or Path(f"/tmp/{record_id[:12]}")
    out_dir.mkdir(parents=True, exist_ok=True)
    post = records.load(record_file)
    blocks = segments.iter_blocks(post.content or "")
    orig_sha = recordbuild.sha256_file(record_file)
    recordbuild.write_workdir(
        post, blocks, out_dir, source=str(record_file), orig_sha256=orig_sha
    )
    print(f"decomposed {record_id[:12]} → {out_dir}")
    print("  manifest.corpus, meta.yaml, bodies/, desc/")
    return 0
