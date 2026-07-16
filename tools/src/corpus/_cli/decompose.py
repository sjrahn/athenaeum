"""Decompose a record into a working dir (manifest + body/desc sidecars).

*(3.1.)* A record with **no stored rendering** (spec §4.1 — `has_stored_rendering` false;
typically an unformed proxy) has an empty content zone (the body is the `body` derivation op,
§6.2). Decomposing it as-is would hand the normalize pass an empty working dir, breaking the
substrate. So on such a record, decompose **derives the body** (the same op as `corpus body`)
into the working dir, and marks the working dir as derived-at-decompose-time so a compile from
it is an *authoring* act, never mistaken for round-tripping stored bytes. A record that
already carries a stored rendering decomposes its stored content zone as-is.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from corpus import paths, recordbuild, records, segments, touches
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

    derived_body: str | None = None
    content = post.content or ""
    if not records.has_stored_rendering(post):
        # Derive the body on demand (the `body` op) so the normalize substrate has content to
        # edit; fall back to whatever the record stores (usually empty) if it can't be derived.
        from corpus.derive import DeriveError, derive_body
        from corpus.store import ArtifactMissing

        try:
            content = derive_body(post, root)
            derived_body = touches.script_identifier("body")
        except (DeriveError, ArtifactMissing) as exc:
            print(f"  note: body not derivable ({exc}); decomposing the stored (empty) record.")

    blocks = segments.iter_blocks(content)
    orig_sha = recordbuild.sha256_file(record_file)
    recordbuild.write_workdir(
        post, blocks, out_dir, source=str(record_file), orig_sha256=orig_sha,
        derived_body=derived_body,
    )
    print(f"decomposed {record_id[:12]} → {out_dir}")
    print("  manifest.corpus, meta.yaml, bodies/, desc/")
    if derived_body:
        print(f"  BODY DERIVED at decompose ({derived_body}) — compiling is authoring, not a "
              "round-trip of stored bytes.")
    return 0
