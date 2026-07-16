"""The retired `corpus redraft` verb + its shared in-memory re-derive core.

*(3.1, §12.19.)* `corpus redraft` is **retired**: its two duties split — re-deriving the
attested layer is `corpus reattest` (never touches the authored layer); re-deriving the
authored layer is a **re-normalize** dispatch through the queue (`corpus enqueue` + the
normalize loop, spec §8.5). `run()` here is a signpost that errors with those pointers,
exactly like the `corpus draft` tombstone (`_cli/draft.py`).

`redraft_record` — the in-memory whole-record re-derive (re-stub + `draft.derive_record`) —
survives as a **test helper**: some fixture-building tests (e.g. `test_eml.py`) still drive
it directly to exercise the attest+derive pipeline without going through the retired CLI
sweep. It is not exposed as a CLI verb.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus import records, restub, touches
from corpus._cli._common import add_corpus_root_arg
from corpus._cli.draft import DraftError, derive_record

__all__ = ["DraftError", "redraft_record"]


def redraft_record(
    record_file: Path, corpus_root: Path, *, fingerprint_cli: bool | None = None
) -> str:
    """Re-derive the record at `record_file` from its artifact, **in memory**; return
    the serialized re-derived record text (NOT written — the caller persists it when not
    a dry run). Idempotent: the in-memory re-stub collapses `touch[]` to the original
    ingest entry (no re-stub touch), so re-deriving an unchanged record reproduces a
    fresh-draft record byte-for-byte. Raises `DraftError` / `ArtifactMissing` when the
    record can't be re-derived."""
    from corpus.draft import mbox_manifest

    post = records.load(record_file)
    chain = touches.touch_list(post)
    # The mbox manifest's declared ordinals are user intent, not derivable from the bytes, and
    # re-stub clears embeds — so capture them before the reset and re-declare them (spec §12.11).
    messages = mbox_manifest.declared_ordinals(post) or None
    stub = restub.restub_post(post, touch_chain=[chain[0]] if chain else [])
    derive_record(stub, corpus_root, fingerprint_cli=fingerprint_cli, messages=messages)
    return records.dumps(stub)


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("target", nargs="?", default=None, help="(retired) record target.")
    parser.add_argument("--mime", default=None, help="(retired) → `corpus reattest --mime`.")
    parser.add_argument("--host", default=None, help="(retired) → `corpus reattest --host`.")
    parser.add_argument(
        "--status", default=None, help="(retired) — status is retired (spec §4.1); see `corpus find --state`."
    )
    parser.add_argument("--force", action="store_true", help="(retired).")
    parser.add_argument("--dry-run", action="store_true", help="(retired) → `corpus reattest --dry-run`.")
    parser.add_argument(
        "--fingerprint", action=argparse.BooleanOptionalAction, default=None,
        help="(retired) → `corpus reattest --fingerprint`.",
    )
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    """`corpus redraft` is retired (3.1, §12.19). Its two duties split: the attested layer
    re-derives via `corpus reattest` (never touches the authored layer, needs no
    normalized-refusal guard); the authored layer re-derives via a re-normalize dispatch
    through the queue (`corpus enqueue <id>`, then the normalize loop, spec §8.5)."""
    sys.stderr.write(
        "corpus redraft is RETIRED (ATH-CORPUS 3.1, §12.19). The bulk re-derive split:\n"
        "  - the attested layer → `corpus reattest` (bulk; never touches the authored layer)\n"
        "  - the authored layer → re-normalize through the queue: `corpus enqueue <id>` "
        "then the normalize loop (spec §8.5)\n"
    )
    del args  # unused — every flag below is a retired pointer, not live behavior
    return 2
