"""`ath ref` — the reference-dataset resolver's CLI slice (spec/ledger.md §6.5).

Reference datasets are linked, not captured per entry: a registered snapshot's
mirror bytes are an ordinary corpus artifact, but its *entries* (a Wikipedia
article, an MBID) are cited `ref://{dataset}[@{tag}]/{id}` and resolved on
demand through the dataset's format adapter — never per-entry records. Three
verbs:

  status    one row per registered dataset x snapshot: adapter availability,
            materialization state (path / store / absent). Fast — filesystem
            stat + store-path lookup only (`refdata.materialize`), no hashing,
            no archive opens.
  resolve   resolve a `ref://` citation through `refdata.resolve` and print
            its content; or field the `corpus://` courtesy redirect (§6.5:
            "Claim evidence citing a mirror's corpus hash directly draws a
            warning: … its content's honest citation surface is `ref://`") —
            this command never resolves corpus records itself, that is
            `corpus resolve`'s job.
  hash      blake3 a candidate mirror file (streamed — mirrors run tens of GB)
            and print a manifest snapshot snippet, the registration helper for
            onboarding a new dataset/tag.

Corpora roots for store-backed materialization are the manifest's own
`corpora:` members (the same derivation `ath ledger`'s `_system` uses) — read
here directly from `ath.manifest` rather than importing `ledger._cli`.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from ath._cli._common import base_parser, resolve_root
from ath.manifest import ManifestError, Reference, load, load_references
from ledger.model import CORPUS_URI_RE, REF_URI_RE

_USAGE = """\
usage: ath ref <command> [options...]

The reference-dataset resolver's CLI slice (spec/ledger.md §6.5).

Commands:
  status              one row per registered dataset x snapshot: adapter
                      availability, materialization state
  resolve URI         resolve a ref:// citation (prints metadata + content);
                      or field a corpus:// courtesy redirect. --meta suppresses
                      the content body
  hash FILE           blake3 a mirror file; print the digest and a
                      ready-to-paste manifest snapshot snippet

All commands but `hash` resolve the manifest (athenaeum.yaml, walked up from
the current directory; --root to point elsewhere).
"""


def _corpora_roots(root: Path) -> list[Path]:
    """Every registered corpus's local root — the store-lookup fallback
    `refdata.materialize` tries after a snapshot's declared `path:` override."""
    return [m.path for m in load(root) if m.layer == "corpora"]


def _materialization_state(reference: Reference, tag: str, corpora_roots: Sequence[Path]) -> str:
    """`path` (the snapshot's declared `path:` override exists), `store` (found
    in a local corpus artifact store), or `absent` — mirrors `refdata.materialize`'s
    own try-path-then-store priority so status agrees with what resolution will
    actually do, without opening or hashing anything."""
    snapshot = reference.snapshots[tag]
    if snapshot.path is not None and Path(snapshot.path).is_file():
        return "path"
    from refdata import materialize

    return "store" if materialize(reference, tag, corpora_roots) is not None else "absent"


def _cmd_status(argv: Sequence[str]) -> int:
    ap = base_parser("ath ref status", "One row per registered dataset x snapshot.")
    ns = ap.parse_args(list(argv))
    root = resolve_root(ns.root)
    refs = load_references(root)
    if not refs:
        print("no reference datasets registered")
        return 0
    from refdata import adapter_available

    corpora_roots = _corpora_roots(root)
    for reference in refs:
        avail = "available" if adapter_available(reference.adapter) else "UNAVAILABLE"
        print(f"{reference.dataset}  adapter={reference.adapter} ({avail})  "
              f"{reference.description}")
        for tag in reference.snapshots:
            marker = " (latest)" if tag == reference.latest else ""
            snapshot = reference.snapshots[tag]
            state = _materialization_state(reference, tag, corpora_roots)
            print(f"  {tag}{marker}  {snapshot.artifact[:12]}  {state}")
    return 0  # status is informational — never a failing exit


def _resolve_ref(
    root: Path, dataset: str, tag: str | None, native_id: str, *, meta_only: bool
) -> int:
    refs = {r.dataset: r for r in load_references(root)}
    reference = refs.get(dataset)
    if reference is None:
        print(f"ath ref resolve: unregistered dataset {dataset!r}", file=sys.stderr)
        return 1

    from refdata import resolve
    from refdata.errors import AdapterUnavailable, EntryNotFound, MirrorUnavailable, UnknownTag

    try:
        entry = resolve(reference, native_id, tag=tag, corpora_roots=_corpora_roots(root))
    except UnknownTag as e:
        print(f"ath ref resolve: unknown snapshot tag — {e}", file=sys.stderr)
        return 1
    except AdapterUnavailable as e:
        print(f"ath ref resolve: adapter unavailable — {e}", file=sys.stderr)
        return 1
    except MirrorUnavailable as e:
        print(f"ath ref resolve: mirror unavailable — {e}", file=sys.stderr)
        return 1
    except EntryNotFound as e:
        print(f"ath ref resolve: entry not found — {e}", file=sys.stderr)
        return 1

    header = f"{entry.dataset}@{entry.tag}  {entry.canonical_id}"
    if entry.canonical_id != entry.native_id:
        header += f"  (redirected from {entry.native_id!r})"
    print(header)
    print(f"title: {entry.title if entry.title is not None else '(none)'}")
    print(f"content-type: {entry.content_type if entry.content_type is not None else '(none)'}")
    print(f"artifact: {entry.artifact[:12]}")
    if not meta_only:
        print()
        print(entry.text if entry.text is not None else "(no text projection)")
    return 0


def _resolve_corpus_redirect(root: Path, hexhash: str) -> int:
    """§6.5's courtesy redirect: a `corpus://` hash that names a registered
    mirror artifact is pointed at its honest citation surface — this command
    never resolves corpus record content, that stays `corpus resolve`'s job."""
    for reference in load_references(root):
        for tag, snapshot in reference.snapshots.items():
            if snapshot.artifact == hexhash:
                print(f"corpus://{hexhash} is the mirror artifact for "
                      f"{reference.dataset}@{tag} — its content's citation surface is "
                      f"ref://{reference.dataset}/{{id}} (spec/ledger.md §6.5). This command "
                      "never resolves corpus record content; that is `corpus resolve`'s job.")
                return 0
    print(f"ath ref resolve: corpus://{hexhash} is not a registered mirror artifact — "
          "this command only redirects mirror-artifact hashes to their ref:// surface; "
          "for an ordinary corpus record use `corpus resolve`.", file=sys.stderr)
    return 1


def _cmd_resolve(argv: Sequence[str]) -> int:
    ap = base_parser("ath ref resolve", "Resolve a ref:// citation, or field a corpus:// redirect.")
    ap.add_argument("uri")
    ap.add_argument("--meta", action="store_true", help="print the metadata header only")
    ns = ap.parse_args(list(argv))
    root = resolve_root(ns.root)

    m = CORPUS_URI_RE.match(ns.uri)
    if m:
        return _resolve_corpus_redirect(root, m.group(1))
    m = REF_URI_RE.match(ns.uri)
    if not m:
        print(f"ath ref resolve: not a ref:// or corpus:// URI: {ns.uri!r}", file=sys.stderr)
        return 2
    dataset, tag, native_id = m.group(1), m.group(2), m.group(3)
    return _resolve_ref(root, dataset, tag, native_id, meta_only=ns.meta)


def _cmd_hash(argv: Sequence[str]) -> int:
    # Not `base_parser` — a pure local hashing helper, no manifest to resolve.
    ap = argparse.ArgumentParser(
        prog="ath ref hash", description="blake3 a mirror file; print a manifest snapshot snippet."
    )
    ap.add_argument("file", type=Path)
    ns = ap.parse_args(list(argv))

    from corpus.hashing import hash_file

    # Mirrors run tens of GB — hash_file streams in 1 MiB chunks (spec §6.5:
    # "versioned, bulk-distributed" mirrors, not a per-entry corpus artifact).
    digest = hash_file(ns.file, also=())["blake3"]
    print(digest)
    print()
    print(f"artifact: {digest}")
    print(f"path: {ns.file.resolve()}")
    return 0


def run(argv: Sequence[str]) -> int:
    args = list(argv)
    if not args or args[0] in ("-h", "--help", "help"):
        print(_USAGE, end="")
        return 0
    cmd, rest = args[0], args[1:]
    handlers = {"status": _cmd_status, "resolve": _cmd_resolve, "hash": _cmd_hash}
    if cmd not in handlers:
        print(f"ath ref: unknown command {cmd!r}", file=sys.stderr)
        print("Run 'ath ref --help' to see available commands.", file=sys.stderr)
        return 2
    try:
        return handlers[cmd](rest)
    except ManifestError as e:
        print(f"ath ref: {e}", file=sys.stderr)
        return 2
