"""`ath ref` — the reference-dataset resolver's CLI slice (spec/ledger.md §6.5).

Reference datasets are linked, not captured per entry: a registered snapshot's
mirror bytes are an ordinary corpus artifact, but its *entries* (a Wikipedia
article, an MBID) are cited `ref://{dataset}[@{tag}]/{id}` and resolved on
demand through the dataset's format adapter — never per-entry records. Five
verbs:

  status    one row per registered dataset x snapshot: adapter availability,
            materialization state (path / store / absent), and — for
            snapshots of an adapter that carries a sidecar index (`osm-pbf`)
            and is materialized locally — its index state (indexed / missing
            / stale). Fast — filesystem stat + store-path lookup only
            (`refdata.materialize`), no hashing, no archive opens (index
            state is a sqlite metadata read, not a rescan).
  resolve   resolve a `ref://` citation through `refdata.resolve` and print
            its content; or field the `corpus://` courtesy redirect (§6.5:
            "Claim evidence citing a mirror's corpus hash directly draws a
            warning: … its content's honest citation surface is `ref://`") —
            this command never resolves corpus records itself, that is
            `corpus resolve`'s job.
  search    the discovery step ahead of `resolve` (§6.5): search a dataset by
            words, print candidate native ids — ids aren't guessable, so a
            ledger scribe searches first and pastes a hit's id into `resolve`
            or straight into a `ref://` citation. Blends title-index and
            full-text hits by default (`--mode` narrows to one tier). A hit
            carrying disambiguating context (e.g. an osm-pbf element's
            classifying tag and coordinates) prints a third column.
  index     (re)build a dataset's sidecar index (`refdata.adapters.osm_pbf`'s
            optional index API) — some formats are a compressed stream with
            no random access and no search index of their own, so `resolve`/
            `search` against them raise `MirrorUnindexed` until this has run
            once. A no-op error for an adapter that needs no sidecar (zim
            mirrors are born indexed).
  hash      blake3 a candidate mirror file (streamed — mirrors run tens of GB)
            and print a manifest snapshot snippet, the registration helper for
            onboarding a new dataset/tag.

Corpora roots for store-backed materialization are the manifest's own
`corpora:` members (the same derivation `ath ledger`'s `_system` uses) — read
here directly from `ath.manifest` rather than importing `ledger._cli`.
"""

from __future__ import annotations

import argparse
import datetime as _dt
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
  search DATASET Q    search a dataset by words; print candidate native ids
                      (id<TAB>title, or id<TAB>title<TAB>context when the
                      adapter supplies disambiguating context, one per line).
                      --tag pins a snapshot, --limit caps the hit count
                      (default 10), --mode picks blend (default) / suggest
                      (title only) / fulltext
  index DATASET       (re)build a dataset's sidecar index (adapters that need
                      one, e.g. osm-pbf). --tag pins a snapshot (default: the
                      dataset's latest)
  hash FILE           blake3 a mirror file; print the digest and a
                      ready-to-paste manifest snapshot snippet

All commands but `hash` resolve the manifest (athenaeum.yaml, walked up from
the current directory; --root to point elsewhere).
"""


def _corpora_roots(root: Path) -> list[Path]:
    """Every registered corpus's local root — the store-lookup fallback
    `refdata.materialize` tries after a snapshot's declared `path:` override."""
    return [m.path for m in load(root) if m.layer == "corpora"]


def _materialization_state(
    reference: Reference, tag: str, corpora_roots: Sequence[Path]
) -> tuple[str, Path | None]:
    """(`path`|`store`|`absent`, the materialized path or None) — mirrors
    `refdata.materialize`'s own try-path-then-store priority so status agrees
    with what resolution will actually do, without opening or hashing
    anything. The path is returned too (not just the state label) so a caller
    wanting the adapter's `index_state` for this snapshot doesn't have to
    materialize a second time."""
    snapshot = reference.snapshots[tag]
    if snapshot.path is not None and Path(snapshot.path).is_file():
        return "path", Path(snapshot.path)
    from refdata import materialize

    mirror_path = materialize(reference, tag, corpora_roots)
    return ("store", mirror_path) if mirror_path is not None else ("absent", None)


def _cmd_status(argv: Sequence[str]) -> int:
    ap = base_parser("ath ref status", "One row per registered dataset x snapshot.")
    ns = ap.parse_args(list(argv))
    root = resolve_root(ns.root)
    refs = load_references(root)
    if not refs:
        print("no reference datasets registered")
        return 0
    from refdata import ADAPTERS, adapter_available

    corpora_roots = _corpora_roots(root)
    for reference in refs:
        avail = "available" if adapter_available(reference.adapter) else "UNAVAILABLE"
        print(f"{reference.dataset}  adapter={reference.adapter} ({avail})  "
              f"{reference.description}")
        # Sidecar index state only for an adapter that carries one (osm-pbf)
        # and only when its optional dependency is actually importable here —
        # a zim row (no `index_state`) or an unavailable adapter is unchanged.
        index_state_fn = None
        if avail == "available":
            index_state_fn = getattr(ADAPTERS[reference.adapter], "index_state", None)
        for tag in reference.snapshots:
            marker = " (latest)" if tag == reference.latest else ""
            snapshot = reference.snapshots[tag]
            state, mirror_path = _materialization_state(reference, tag, corpora_roots)
            row = f"  {tag}{marker}  {snapshot.artifact[:12]}  {state}"
            if index_state_fn is not None and mirror_path is not None:
                row += f"  index={index_state_fn(mirror_path)}"
            print(row)
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
    from refdata.errors import (
        AdapterUnavailable,
        EntryNotFound,
        MirrorCorrupt,
        MirrorUnavailable,
        MirrorUnindexed,
        UnknownTag,
    )

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
    except MirrorCorrupt as e:
        print(f"ath ref resolve: mirror file corrupt or still downloading: {e}", file=sys.stderr)
        return 1
    except MirrorUnindexed as e:
        print(f"ath ref resolve: mirror not indexed — {e}", file=sys.stderr)
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
    # Full hash: verify compares stamped bindings against the manifest's 64-hex
    # value, so a truncated print here would seed drift-warning stamps.
    print(f"artifact: {entry.artifact}")
    if meta_only:
        today = _dt.date.today().isoformat()
        print(f'binding: {{"snapshot": "{entry.tag}", '
              f'"artifact": "{entry.artifact}", "at": "{today}"}}')
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


def _cmd_search(argv: Sequence[str]) -> int:
    ap = base_parser(
        "ath ref search", "Search a dataset by words; print candidate native ids."
    )
    ap.add_argument("dataset")
    ap.add_argument("query")
    ap.add_argument("--tag", default=None, help="pin a snapshot (default: the dataset's latest)")
    ap.add_argument("--limit", type=int, default=10, help="max hits to print (default 10)")
    ap.add_argument(
        "--mode", choices=("blend", "suggest", "fulltext"), default="blend",
        help="blend (default): title hits then full-text hits, deduplicated; "
             "suggest: title index only; fulltext: full-text index only",
    )
    ns = ap.parse_args(list(argv))
    root = resolve_root(ns.root)

    refs = {r.dataset: r for r in load_references(root)}
    reference = refs.get(ns.dataset)
    if reference is None:
        print(f"ath ref search: unregistered dataset {ns.dataset!r}", file=sys.stderr)
        return 1

    from refdata import search
    from refdata.errors import (
        AdapterUnavailable,
        MirrorCorrupt,
        MirrorUnavailable,
        MirrorUnindexed,
        UnknownTag,
    )

    try:
        hits = search(
            reference, ns.query, tag=ns.tag, corpora_roots=_corpora_roots(root), limit=ns.limit,
            mode=ns.mode,
        )
    except UnknownTag as e:
        print(f"ath ref search: unknown snapshot tag — {e}", file=sys.stderr)
        return 1
    except AdapterUnavailable as e:
        print(f"ath ref search: adapter unavailable — {e}", file=sys.stderr)
        return 1
    except MirrorUnavailable as e:
        print(f"ath ref search: mirror unavailable — {e}", file=sys.stderr)
        return 1
    except MirrorCorrupt as e:
        print(f"ath ref search: mirror file corrupt or still downloading: {e}", file=sys.stderr)
        return 1
    except MirrorUnindexed as e:
        print(f"ath ref search: mirror not indexed — {e}", file=sys.stderr)
        return 1

    resolved_tag = ns.tag if ns.tag is not None else reference.latest
    print(f"{reference.dataset}@{resolved_tag}  {len(hits)} hit(s)", file=sys.stderr)
    if not hits:
        print("ath ref search: no hits", file=sys.stderr)
        return 0
    for hit in hits:
        title = hit.title if hit.title is not None else "(no title)"
        if hit.context is not None:
            print(f"{hit.native_id}\t{title}\t{hit.context}")
        else:
            print(f"{hit.native_id}\t{title}")
    return 0


def _cmd_index(argv: Sequence[str]) -> int:
    ap = base_parser(
        "ath ref index", "(Re)build a dataset's sidecar index (adapters that need one)."
    )
    ap.add_argument("dataset")
    ap.add_argument("--tag", default=None, help="pin a snapshot (default: the dataset's latest)")
    ns = ap.parse_args(list(argv))
    root = resolve_root(ns.root)

    refs = {r.dataset: r for r in load_references(root)}
    reference = refs.get(ns.dataset)
    if reference is None:
        print(f"ath ref index: unregistered dataset {ns.dataset!r}", file=sys.stderr)
        return 1

    tag = ns.tag if ns.tag is not None else reference.latest
    if tag not in reference.snapshots:
        print(
            f"ath ref index: unknown snapshot tag — {reference.dataset}: {tag!r} is not "
            "a registered snapshot",
            file=sys.stderr,
        )
        return 1

    from refdata import ADAPTERS, adapter_available

    if not adapter_available(reference.adapter):
        print(
            f"ath ref index: adapter unavailable — {reference.dataset}: adapter "
            f"{reference.adapter!r} is unregistered or its optional dependency is not "
            "installed in this environment",
            file=sys.stderr,
        )
        return 1

    adapter_module = ADAPTERS[reference.adapter]
    build_index = getattr(adapter_module, "build_index", None)
    if build_index is None:
        print(
            f"ath ref index: adapter '{reference.adapter}' needs no sidecar index",
            file=sys.stderr,
        )
        return 1

    from refdata import materialize
    from refdata.errors import MirrorCorrupt

    mirror_path = materialize(reference, tag, _corpora_roots(root))
    if mirror_path is None:
        print(
            f"ath ref index: mirror unavailable — {reference.dataset}@{tag}: no local "
            "bytes (neither the declared path: override nor any given corpus root's "
            "artifact store)",
            file=sys.stderr,
        )
        return 1

    # Chatty per-batch progress would flood stderr on a real multi-GB extract
    # (~55M tagged elements over ~1000 flushes on the Canada extract) — print
    # only every 5M elements' worth of progress.
    last_reported = 0

    def progress(elements: int) -> None:
        nonlocal last_reported
        if elements - last_reported >= 5_000_000:
            print(f"  indexed {elements:,} elements...", file=sys.stderr)
            last_reported = elements

    try:
        counts = build_index(mirror_path, progress=progress)
    except MirrorCorrupt as e:
        print(f"ath ref index: mirror file corrupt or still downloading: {e}", file=sys.stderr)
        return 1

    # Confirm the build actually left the sidecar in a state resolve/search
    # will accept — the CLI never hardcodes the sidecar's own path/suffix,
    # that's the adapter's business (`refdata.adapters` module docstring).
    if adapter_module.index_state(mirror_path) != "indexed":
        print(
            f"ath ref index: {reference.dataset}@{tag}: build_index reported success but "
            "index_state is not 'indexed' — this is an adapter bug, not a data condition",
            file=sys.stderr,
        )
        return 1
    elements = counts.get("elements", 0)
    named = counts.get("named", 0)
    print(f"{reference.dataset}@{tag}: indexed {elements:,} element(s) ({named:,} named)")
    return 0


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
    handlers = {
        "status": _cmd_status,
        "resolve": _cmd_resolve,
        "search": _cmd_search,
        "index": _cmd_index,
        "hash": _cmd_hash,
    }
    if cmd not in handlers:
        print(f"ath ref: unknown command {cmd!r}", file=sys.stderr)
        print("Run 'ath ref --help' to see available commands.", file=sys.stderr)
        return 2
    try:
        return handlers[cmd](rest)
    except ManifestError as e:
        print(f"ath ref: {e}", file=sys.stderr)
        return 2
