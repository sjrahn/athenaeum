"""Resolve and stamp a video stream leaf's cut strategy — `corpus cut` (spec §7.2.1, 3.11).

    corpus cut <leaf-id> [--write]          one promoted stream leaf
    corpus cut <container-id> [--write]     every video stream the container rosters

The mechanical half of video segmentation. Resolves the cut strategy (mime default ← the
container's origin overlay), runs its detector against the **container's** timeline, and writes
the resulting `cutting:` stamp onto the leaf's artifact block. The `time_range=` markers
themselves are not stored: the body derivation (`corpus body`, `corpus://<leaf>?body`) emits
them from the stamped strategy, exactly as an HTML record's `el=` addresses are re-derived from
its stamped `addressing:` parse.

**Dry-run by default.** The stamp is what a record's `time_range=` addresses rest on, so
writing one is not a neutral act — `--write` is required. (The lesson of `corpus compile`,
which shipped without one.)

**Re-stamping compares before it writes** (§7.2.1's second rule). A leaf that already carries a
stamp is re-derived under *its own stamped strategy*, never a fresh resolution: an unchanged
count refreshes and moves nothing; a changed count **holds** the record and reports both
numbers, because re-segmentation moves every address out from under whatever cites it and that
is an authoring decision, not a sweep's.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import frontmatter

from corpus import cut as cut_mod
from corpus import mime, paths, records, touches
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root

_STREAM_RESULT_KEYS = ("cuts", "duration")


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "record", help="A promoted stream leaf's id, or a container id (cuts its video streams)."
    )
    parser.add_argument(
        "--write", action="store_true",
        help="apply the stamp (default: report only — the stamp is what addresses rest on).",
    )
    parser.add_argument(
        "--force", action="store_true",
        help="re-stamp even when the derived cut count disagrees with the attested one. "
             "This RE-POINTS every time_range= address on the record; re-segment the authored "
             "layer in the same change.",
    )
    parser.add_argument(
        "--regenerate", action="store_true", help="ignore the resolver's cached cut list."
    )
    parser.add_argument("--json", action="store_true", help="emit the result as JSON.")
    add_corpus_root_arg(parser)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    record_file = paths.record_path(corpus_root, args.record)
    if not record_file.is_file():
        sys.exit(f"no record for {args.record} at {record_file}")
    post = records.load(record_file)
    media_type = records.media_type_for(post)

    targets = _targets(corpus_root, post, args.record, media_type)
    if not targets:
        sys.exit(
            f"{args.record[:12]} ({media_type or 'unknown type'}) is neither a promoted "
            f"stream leaf (no containment-lineage origin naming a stream) nor a container "
            f"rostering a video stream — nothing to cut."
        )

    results: list[dict[str, Any]] = []
    exit_code = 0
    for leaf_id, leaf_file in targets:
        outcome = _cut_one(
            corpus_root, leaf_id, leaf_file,
            write=args.write, force=args.force, regenerate=args.regenerate,
        )
        results.append(outcome)
        if outcome["status"] in ("held", "unresolved"):
            exit_code = 1

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2))
    else:
        for r in results:
            _print_human(r, wrote=args.write)
        if not args.write and any(r["status"] == "ready" for r in results):
            print("\n(dry run — pass --write to apply the stamp)")
    return exit_code


# ---------- internals ---------- #


def _targets(
    corpus_root: Path, post: frontmatter.Post, record_id: str, media_type: str
) -> list[tuple[str, Path]]:
    """The leaves to cut: the record itself when it is a stream leaf, else the video-stream
    members its roster declares that have actually been promoted.

    A rostered-but-unpromoted stream is skipped rather than promoted here: minting a record is
    `corpus promote`'s job and doing it as a side effect of a cut would hide it.
    """
    if cut_mod.stream_lineage(post) is not None:
        return [(record_id, paths.record_path(corpus_root, record_id))]

    out: list[tuple[str, Path]] = []
    for row in records.iter_members(post):
        if not str(row.get("media_type") or "").startswith("video/"):
            continue
        transport = str(row.get("transport") or "")
        _, _, hexval = transport.partition(":")
        if not hexval:
            continue
        leaf_file = paths.record_path(corpus_root, hexval)
        if leaf_file.is_file():
            out.append((hexval, leaf_file))
    return out


def _cut_one(
    corpus_root: Path,
    leaf_id: str,
    leaf_file: Path,
    *,
    write: bool,
    force: bool,
    regenerate: bool,
) -> dict[str, Any]:
    post = records.load(leaf_file)
    lineage = cut_mod.stream_lineage(post)
    if lineage is None:
        return {
            "leaf": leaf_id, "status": "unresolved",
            "reason": "no containment-lineage origin naming a container stream",
        }
    container_id, stream_address = lineage
    container_file = paths.record_path(corpus_root, container_id)
    if not container_file.is_file():
        return {
            "leaf": leaf_id, "status": "unresolved",
            "reason": f"container record {container_id[:12]} is absent",
        }
    container_post = records.load(container_file)

    existing = records.cutting(post)
    strategy = None
    if existing is not None:
        # Re-stamping runs the leaf's OWN stamped strategy. Re-resolving here would let an
        # overlay edit silently re-cut the fleet — the exact drift the count check exists to
        # detect, arriving through the checker itself.
        strategy = {k: v for k, v in existing.items() if k not in _STREAM_RESULT_KEYS}

    try:
        container_path = _container_bytes(corpus_root, container_id, container_post)
    except Exception as exc:  # ArtifactMissing and kin — the duration probe's fallback only
        container_path = None
        if not ((records.artifact_block(container_post) or {}).get("fields") or {}).get(
            "duration"
        ):
            return {
                "leaf": leaf_id, "status": "unresolved",
                "reason": f"no attested duration and the container's bytes are unavailable: {exc}",
            }

    from corpus.store import ArtifactMissing

    try:
        outcome = cut_mod.cut_stream(
            corpus_root, container_post, container_id, stream_address,
            container_path=container_path, strategy=strategy, regenerate=regenerate,
        )
    except (cut_mod.Unresolved, NotImplementedError, ArtifactMissing) as exc:
        # `artifacts/` is gitignored, so absent bytes are an everyday state and not a defect
        # — a detector-backed strategy simply cannot run. Report it; never traceback.
        return {"leaf": leaf_id, "status": "unresolved", "reason": str(exc)}

    result: dict[str, Any] = {
        "leaf": leaf_id,
        "container": container_id,
        "stream": stream_address,
        "strategy": outcome.strategy,
        "duration": outcome.duration,
        "raw_cuts": outcome.raw_cut_count,
        "spans": len(outcome.spans),
        "stamp": outcome.stamp,
        "signals": [{"id": s.id, "detail": s.detail} for s in outcome.signals],
        "first_addresses": outcome.addresses[:5],
    }

    attested = (existing or {}).get("cuts")
    if isinstance(attested, int) and attested != len(outcome.spans) and not force:
        result.update({"status": "held", "attested_cuts": attested})
        return result
    if existing is not None and attested == len(outcome.spans):
        result["status"] = "refreshed"
    else:
        result["status"] = "ready"

    if write:
        artifact = records.artifact_block(post) or {"mime": records.media_type_for(post),
                                                    "fields": {}}
        fields = dict(artifact.get("fields") or {})
        if fields.get("cutting") == outcome.stamp:
            result["status"] = "unchanged"
            return result
        fields["cutting"] = outcome.stamp
        records.set_artifact_block(post, mime=str(artifact.get("mime") or ""), fields=fields)
        touches.record_touch(post, touches.script_identifier("cut"))
        records.dump(post, leaf_file)
        result["status"] = "stamped"
    return result


def _container_bytes(corpus_root: Path, container_id: str, container_post) -> Path:
    from corpus import containment

    return containment.ensure_local_bytes(
        corpus_root, container_id, mime.extension_for(records.media_type_for(container_post))
    )


def _print_human(r: dict[str, Any], *, wrote: bool) -> None:
    status = r["status"]
    print(f"{status}: {r['leaf'][:12]}")
    if status == "unresolved":
        print(f"  reason: {r['reason']}")
        return
    print(f"  container:  {r['container'][:12]}?{r['stream']}")
    print(f"  strategy:   {r['strategy'].get('id')} {_params(r['strategy'])}")
    print(f"  timeline:   {r['duration']}s → {r['spans']} span(s) "
          f"from {r['raw_cuts']} detected cut(s)")
    if status == "held":
        print(f"  HELD:       the stamp attests {r['attested_cuts']} spans, this derivation "
              f"finds {r['spans']}.")
        print("              Re-segmentation moves every time_range= address on this record; "
              "pass --force")
        print("              only together with re-authoring the affected segments.")
    for s in r["signals"]:
        print(f"  signal:     {s['id']} — {s['detail']}")
    if r["first_addresses"]:
        shown = ", ".join(r["first_addresses"])
        more = "" if r["spans"] <= len(r["first_addresses"]) else ", …"
        print(f"  addresses:  {shown}{more}")


def _params(strategy: dict[str, Any]) -> str:
    rest = {k: v for k, v in strategy.items() if k != "id"}
    return f"({', '.join(f'{k}={v}' for k, v in rest.items())})" if rest else ""


def cut_leaf_stamp(
    corpus_root: Path,
    container_post: frontmatter.Post,
    container_id: str,
    stream_address: str,
    *,
    container_path: Path | None = None,
) -> tuple[dict[str, Any] | None, str]:
    """The stamp `corpus promote` writes onto a freshly minted stream leaf, plus a note.

    Promotion is the one moment both records are legitimately in hand (§7.2.1), so it is where
    the resolution happens. But a promote must never FAIL for want of a strategy: an
    unresolved or undetectable cut leaves the leaf unstamped — a legitimate state — and returns
    the reason so the caller can print it instead of leaving the omission silent.
    """
    try:
        outcome = cut_mod.cut_stream(
            corpus_root, container_post, container_id, stream_address,
            container_path=container_path,
        )
    except (cut_mod.Unresolved, NotImplementedError, OSError, RuntimeError) as exc:
        return None, f"not cut ({exc})"
    note = f"{len(outcome.spans)} span(s) under {outcome.strategy.get('id')}"
    if outcome.signals:
        note += " — " + "; ".join(s.id for s in outcome.signals)
    return outcome.stamp, note
