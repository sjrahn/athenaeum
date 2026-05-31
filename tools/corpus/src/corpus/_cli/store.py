"""`corpus store` — interact with the configured ArtifactStore.

Subcommands:

- `status` — diff local vs remote (set difference both ways). For a local-only
  store this prints the local set and notes that no remote is configured.
- `push <hash>` — re-upload an existing local artifact (idempotent; safe to repeat).
  No-op on a local-only store.
- `pull` — download every remote-only artifact to the local cache.
- `fetch <hash>` — hydrate a single artifact by hash (downloads if absent).
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    sub = parser.add_subparsers(dest="action", required=True, metavar="ACTION")

    p_status = sub.add_parser("status", help="Diff local vs remote artifacts.")
    add_corpus_root_arg(p_status)

    p_push = sub.add_parser("push", help="Re-upload an artifact to the remote store.")
    p_push.add_argument("hash", help="Record hash (or unique hex prefix).")
    add_corpus_root_arg(p_push)

    p_pull = sub.add_parser("pull", help="Download every remote-only artifact.")
    add_corpus_root_arg(p_pull)

    p_fetch = sub.add_parser("fetch", help="Hydrate a single artifact by hash.")
    p_fetch.add_argument("hash", help="Record hash (or unique hex prefix).")
    add_corpus_root_arg(p_fetch)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    if args.action == "status":
        return _status(corpus_root)
    if args.action == "push":
        return _push(corpus_root, args.hash)
    if args.action == "pull":
        return _pull(corpus_root)
    if args.action == "fetch":
        return _fetch(corpus_root, args.hash)
    print(f"unknown action: {args.action}", file=sys.stderr)
    return 2


# ---------- handlers ---------- #


def _status(corpus_root: Path) -> int:
    from corpus.store import LocalArtifactStore, get_store

    store = get_store(corpus_root)
    local = store.list_local()
    print(f"backend: {type(store).__name__}")
    print(f"local artifacts:  {len(local)}")
    if isinstance(store, LocalArtifactStore):
        print("remote: (none — local-only store)")
        return 0
    remote = store.list_remote()
    only_local = sorted(local - remote)
    only_remote = sorted(remote - local)
    both = local & remote
    print(f"remote artifacts: {len(remote)}")
    print(f"in both:          {len(both)}")
    print(f"local-only:       {len(only_local)}")
    print(f"remote-only:      {len(only_remote)}")
    if only_local:
        print("\nlocal-only (push to mirror):")
        for n in only_local[:50]:
            print(f"  {n}")
        if len(only_local) > 50:
            print(f"  ... and {len(only_local) - 50} more")
    if only_remote:
        print("\nremote-only (pull to hydrate):")
        for n in only_remote[:50]:
            print(f"  {n}")
        if len(only_remote) > 50:
            print(f"  ... and {len(only_remote) - 50} more")
    return 0


def _push(corpus_root: Path, target: str) -> int:
    """Re-upload a single artifact via the store's `put`.

    `put` writes to both local cache and remote (Azure/S3 adapters re-upload an
    existing local copy; LocalArtifactStore re-copies in-place, no-op).
    """
    from corpus import paths
    from corpus.store import LocalArtifactStore, get_store

    record_id, _ = paths.resolve_record(corpus_root, target)
    store = get_store(corpus_root)
    if isinstance(store, LocalArtifactStore):
        print("push: no-op (local-only store)")
        return 0
    # Discover the artifact's extension via list_local.
    shard_prefix = f"{record_id[:2]}/{record_id}."
    candidates = [n for n in store.list_local() if n.startswith(shard_prefix)]
    if not candidates:
        sys.exit(f"no local artifact for {record_id}")
    name = candidates[0]
    ext = name.split(".", 1)[1]
    src = store.local_path(record_id, ext)
    store.put(record_id, ext, src)
    print(f"pushed: {name}")
    return 0


def _pull(corpus_root: Path) -> int:
    from corpus.store import LocalArtifactStore, get_store

    store = get_store(corpus_root)
    if isinstance(store, LocalArtifactStore):
        print("pull: no-op (local-only store)")
        return 0
    local = store.list_local()
    remote = store.list_remote()
    pending = sorted(remote - local)
    if not pending:
        print("pull: already up to date")
        return 0
    print(f"pull: hydrating {len(pending)} artifact(s)…")
    for name in pending:
        # name is "<shard>/<id>.<ext>"; split.
        try:
            shard_id, ext = name.split(".", 1)
            _shard, rid = shard_id.split("/", 1)
        except ValueError:
            print(f"  skip (unparseable name): {name}", file=sys.stderr)
            continue
        store.ensure_local(rid, ext)
    return 0


def _fetch(corpus_root: Path, target: str) -> int:
    from corpus import paths
    from corpus.store import LocalArtifactStore, get_store

    record_id, _ = paths.resolve_record(corpus_root, target)
    store = get_store(corpus_root)
    if isinstance(store, LocalArtifactStore):
        # Already-local artifact: report; absent: error.
        local_names = [n for n in store.list_local() if n.startswith(f"{record_id[:2]}/{record_id}.")]
        if local_names:
            print(f"already local: {local_names[0]}")
            return 0
        print(f"no local artifact for {record_id} (local-only store; nothing to fetch)")
        return 1
    # Cloud: find by extension via list_remote.
    shard_prefix = f"{record_id[:2]}/{record_id}."
    candidates = [n for n in store.list_remote() if n.startswith(shard_prefix)]
    if not candidates:
        sys.exit(f"no remote artifact for {record_id}")
    name = candidates[0]
    ext = name.split(".", 1)[1]
    p = store.ensure_local(record_id, ext)
    print(f"fetched: {p}")
    return 0
