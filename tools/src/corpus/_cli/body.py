"""Stream a record's body to stdout.

The stored content zone when the record has one (a normalized record's authored body, or a
2.x draft's grandfathered mechanical body); otherwise the **derived** body — the `body` op
(§6.2), which re-runs the mime drafter over the artifact on demand — so a 3.0 stub whose
content zone is empty (bytes not stored as a body) is still readable. `--derived` forces the
derivation even when a stored body exists."""

from __future__ import annotations

import argparse
import sys

from corpus import paths, records
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", help="Hash, hex prefix, or record file path.")
    parser.add_argument(
        "--derived",
        action="store_true",
        help="Always derive the body from the artifact (ignore any stored content zone).",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    root = resolved_corpus_root(args)
    _, record_file = paths.resolve_record(root, args.target)
    post = records.load(record_file)

    stored = post.content or ""
    if stored.strip() and not args.derived:
        text = stored
    else:
        from corpus.derive import DeriveError, derive_body
        from corpus.store import ArtifactMissing

        try:
            text = derive_body(post, root)
        except (DeriveError, ArtifactMissing) as exc:
            sys.exit(f"cannot derive body: {exc}")

    sys.stdout.write(text)
    if not text.endswith("\n"):
        sys.stdout.write("\n")
    return 0
