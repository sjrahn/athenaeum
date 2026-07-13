"""Test helper: draft a record via the retained `derive_record` core.

The `corpus draft` VERB is retired in 3.0 — ingest attests, the `body` op derives, normalize
authors. But `derive_record` survives as the transitional whole-record drafting path (attest +
store the mechanical body + `status: draft`) that `corpus redraft` still calls. Tests that
assert on the *drafted record shape* (the body segments a drafter builds) route through here."""

from __future__ import annotations

from pathlib import Path

from corpus import paths, records
from corpus._cli import draft as _draft_cli
from corpus.draft import mbox_manifest


def draft_for_test(corpus_root: Path, target: str, messages: str | None = None) -> int:
    """Draft the record `target` in `corpus_root` in place via `derive_record`; return 0.
    `messages` is the mbox selective declaration (a `--messages`-style spec string)."""
    _, rf = paths.resolve_record(corpus_root, target)
    post = records.load(rf)
    ords = mbox_manifest.parse_message_spec(messages) if messages else None
    _draft_cli.derive_record(post, corpus_root, messages=ords)
    records.dump(post, rf)
    return 0
