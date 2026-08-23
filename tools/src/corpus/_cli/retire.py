"""Container retirement — extend or die (spec §12.8, v37 owner ruling).

`corpus retire <container>` resolves the fourth-guard containment stalemate `corpus rm`
only refuses (never repairs): a container record with promoted member records. Every
such member, in one sweep, resolves in exactly one of two ways, decided by bytes:

- **extend** — some OTHER live container (any container record besides the one
  retiring) carries the byte-identical member, found by the same member-index blake3
  lookup `corpus rm`'s containment guard already builds (`containment.build_member_
  index`). The member re-points to it via the §8.1 promote fold path — driving
  `corpus promote` of the SAME member address under the live container, which verifies
  the blake3 itself and appends a fresh origin block — so it survives with a live
  route; its retired route stays exactly where it was, an earlier origin block, as
  history.
- **die** — no live container carries the bytes: the member record is removed WITH the
  container, in the same sweep, via the same per-record machinery `corpus rm` uses
  (`.md` + artifact + empty shard dirs — INCLUDING a standalone artifact file the
  member happens to have; see below).

A member whose OWN origin lineage already shows independence from the retiring
container — a live containment route into a DIFFERENT container (its embed roster
still declares the member), or a genuine non-containment producer/capture origin
(independently ingested, never solely through `corpus promote`) — needs neither: this
retirement was never what kept it alive, so it is left alone, outside the extend/die
sweep entirely. A materialized standalone ARTIFACT FILE is deliberately NOT this test:
custody is not provenance (spec §12.8, v37 owner ruling) — an operator can `corpus
resolve`/copy bytes into `artifacts/` for any reason, and that copy names no route a
future reader can trust the way an origin block does. A member whose origin lineage
runs ONLY through the retiring container follows extend-or-die strictly regardless of
any artifact file sitting in the store.

There is deliberately no third state (spec §12.8, v37): a member record kept alive on
provenance alone — a transferred-origin husk, an acknowledged tombstone, any route to
bytes that no longer exist — is prohibited. No flag preserves a dying record.

Manifest-first: dry-run by default, printing the full disposition (every extension,
every removal, and the ledger impact — citing claims — of every to-die record, via `ath
ledger worklist` when a ledger root sits beside the corpus root, the instance layout)
before anything is touched. `--apply` executes. Zero partial states: any extend-fold
failure aborts before ANY removal (folding is additive — nothing destructive has
happened yet); the container itself is removed last, after every member is resolved.
"""

from __future__ import annotations

import argparse
import contextlib
import json
import sys
from dataclasses import dataclass, field
from io import StringIO
from pathlib import Path
from typing import Any

from corpus import containment, maintenance, paths, records
from corpus import functional_uri as furi
from corpus._cli import promote as promote_cli
from corpus._cli._common import add_corpus_root_arg, resolved_corpus_root


def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("container", help="container record id / hash prefix to retire.")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="execute the disposition (default: dry-run — prints the plan, touches nothing).",
    )
    parser.add_argument("--json", action="store_true", help="emit the plan/result as JSON.")
    add_corpus_root_arg(parser)


class RetireError(RuntimeError):
    """Raised to abort the sweep before any removal happens — surfaced as a clean exit."""


@dataclass
class ExtendItem:
    member_id: str
    target_container: str
    address: str


@dataclass
class UntouchedItem:
    member_id: str
    reason: str


@dataclass
class RetirePlan:
    container_id: str
    extend: list[ExtendItem] = field(default_factory=list)
    die: list[str] = field(default_factory=list)
    untouched: list[UntouchedItem] = field(default_factory=list)
    ledger_root: Path | None = None
    # record id -> citing-claim rows (`ath ledger worklist` output), or None when no
    # ledger root was reachable to check at all (distinct from "reachable, zero rows").
    citing_claims: dict[str, list[str] | None] = field(default_factory=dict)


@dataclass
class RetireResult:
    extended: list[ExtendItem]
    died: list[str]
    container_removed: str


def _ledger_root_beside(corpus_root: Path) -> Path | None:
    """The instance layout (spec Part I §2.2): `corpus/` and `ledger/` sit side by side
    under one instance root. `ath init` scaffolds `ledger/facts/` unconditionally, so its
    presence is the reachability test — mirrors `paths.find_corpus_root`'s own
    presence-of-known-subdir check, just sideways instead of upward."""
    candidate = corpus_root.parent / "ledger"
    return candidate if (candidate / "facts").is_dir() else None


def _citing_claims(ledger_root: Path | None, record_id: str) -> list[str] | None:
    """`ath ledger worklist <hash>` rows citing `record_id` — the citing-claims
    disclosure the retirement manifest owes every to-die record (spec §12.8, v37) — or
    `None` when no ledger root is reachable to ask at all."""
    if ledger_root is None:
        return None
    from ledger.worklist import worklist

    return worklist(ledger_root, record_id)


def _container_id_from_uri(uri: str) -> str | None:
    if not uri.startswith("corpus://"):
        return None
    try:
        return furi.parse(uri).hash
    except ValueError:
        return None


def _independent_origin(
    corpus_root: Path, member_id: str, retiring_container_id: str
) -> str | None:
    """Whether `member_id`'s OWN origin lineage already shows independence from the
    retiring container: a live containment route into a DIFFERENT container (checked by
    the same declaration test `containment.build_member_index` relies on — its embed
    roster still names this member), or a genuine non-containment origin (a real
    producer/capture uri, or a uri-less local-file drop — either way, never minted
    solely by `corpus promote`). Returns the reason string, or `None` when every origin
    block traces back to the retiring container alone (or nowhere live) — the caller's
    cue to run extend-or-die."""
    post = records.load(paths.record_path(corpus_root, member_id))
    for block in records.iter_origin_blocks(post):
        fields = block.get("fields") or {}
        uri = fields.get("uri")
        uris = uri if isinstance(uri, list) else ([uri] if uri else [])
        if not uris:
            return "independent capture origin (local-file drop, no containment lineage)"
        for u in uris:
            other_id = _container_id_from_uri(str(u))
            if other_id is None:
                return f"independent capture origin: {u}"
            if other_id == retiring_container_id:
                continue
            other_file = paths.record_path(corpus_root, other_id)
            if not other_file.is_file():
                continue  # a dead route — not live, keep looking
            other_post = records.load(other_file)
            if member_id in set(containment.member_hashes(other_post)):
                return f"live containment route via {other_id[:12]}"
    return None


def plan_retirement(corpus_root: Path, container_id: str) -> RetirePlan:
    """Compute, without touching anything, the full disposition for retiring
    `container_id`: every promoted member's extend/die/untouched verdict plus the
    ledger impact of every record that would be removed (the die members AND the
    container itself, which is always removed last regardless of how many members
    extend)."""
    container_file = paths.record_path(corpus_root, container_id)
    if not container_file.is_file():
        raise RetireError(f"no container record for {container_id} at {container_file}")
    post = records.load(container_file)

    member_index = containment.build_member_index(corpus_root)
    extend: list[ExtendItem] = []
    die: list[str] = []
    untouched: list[UntouchedItem] = []
    seen: set[str] = set()
    for member_hex in containment.member_hashes(post):
        if member_hex == container_id or member_hex in seen:
            continue
        seen.add(member_hex)
        if not paths.record_path(corpus_root, member_hex).is_file():
            continue  # not a promoted record — no record-borne bytes for retire to resolve

        reason = _independent_origin(corpus_root, member_hex, container_id)
        if reason is not None:
            untouched.append(UntouchedItem(member_hex, reason))
            continue

        routes = [(c, a) for c, a in member_index.get(member_hex, []) if c != container_id]
        if routes:
            target_container, address = routes[0]
            extend.append(ExtendItem(member_hex, target_container, address))
        else:
            die.append(member_hex)

    ledger_root = _ledger_root_beside(corpus_root)
    to_die_records = [*die, container_id]
    citing_claims = {rid: _citing_claims(ledger_root, rid) for rid in to_die_records}
    return RetirePlan(
        container_id=container_id,
        extend=extend,
        die=die,
        untouched=untouched,
        ledger_root=ledger_root,
        citing_claims=citing_claims,
    )


def _promote_fold(corpus_root: Path, uri: str) -> str:
    """Drive `corpus promote` for one extend (spec §8.1) — identity re-verified via its
    own blake3 check against the streamed member, exactly as an operator-run promote
    would. Returns the outcome (`"folded"` / `"already-promoted"`); raises `RetireError`
    on any failure (stale embed, hash mismatch, missing container) so the sweep aborts
    before touching anything destructive."""
    ns = argparse.Namespace(uri=uri, json=True, corpus_root=str(corpus_root))
    buf = StringIO()
    try:
        with contextlib.redirect_stdout(buf):
            code = promote_cli.run(ns)
    except SystemExit as exc:
        raise RetireError(f"extend-fold failed for {uri}: {exc}") from exc
    if code != 0:
        raise RetireError(f"extend-fold failed for {uri}: {buf.getvalue().strip()}")
    return json.loads(buf.getvalue())["outcome"]


def execute_retirement(corpus_root: Path, plan: RetirePlan) -> RetireResult:
    """Execute a planned retirement: every extend-fold FIRST (additive, non-destructive —
    an abort here leaves the corpus exactly as it was, no partial removal), then every
    die-removal, then the container itself, last."""
    extended: list[ExtendItem] = []
    for item in plan.extend:
        uri = f"corpus://{item.target_container}?{item.address}"
        _promote_fold(corpus_root, uri)
        extended.append(item)

    died: list[str] = []
    if plan.die:
        # A dying member is, by definition, resolved to have no live byte route left —
        # force through any referrer/floor guard `corpus rm` would otherwise raise on
        # its own: the alternative (refusing to remove) is the prohibited third state,
        # a record kept alive on provenance alone.
        result = maintenance.remove_records(corpus_root, plan.die, force=True, execute=True)
        if result.blocked:
            raise RetireError(f"die-removal unexpectedly blocked for: {result.blocked}")
        died = result.removed

    container_result = maintenance.remove_records(
        corpus_root, [plan.container_id], execute=True
    )
    if container_result.blocked:
        raise RetireError(
            f"container removal blocked after every member was resolved — investigate: "
            f"{container_result.blocked} (not forced past — this is a NEW problem "
            f"retirement's own disposition didn't account for)"
        )
    return RetireResult(extended=extended, died=died, container_removed=plan.container_id)


def run(args: argparse.Namespace) -> int:
    corpus_root = resolved_corpus_root(args)
    container_id, _ = paths.resolve_record(corpus_root, args.container)
    try:
        plan = plan_retirement(corpus_root, container_id)
    except RetireError as e:
        sys.exit(str(e))

    if not args.apply:
        if args.json:
            print(json.dumps(_plan_to_dict(plan), ensure_ascii=False, indent=2))
        else:
            _print_plan(plan)
            print("  (dry-run) pass --apply to execute.")
        return 0

    if not args.json:
        _print_plan(plan)
    try:
        result = execute_retirement(corpus_root, plan)
    except RetireError as e:
        sys.exit(f"retire aborted: {e}")

    if args.json:
        print(json.dumps(_result_to_dict(result), ensure_ascii=False, indent=2))
    else:
        _print_result(result)
    return 0


def _print_plan(plan: RetirePlan) -> None:
    print(f"retire {plan.container_id[:12]}:")
    if not plan.extend and not plan.die and not plan.untouched:
        print("  no promoted members — container removes clean.")
    for item in plan.extend:
        print(
            f"  extend    {item.member_id[:12]} -> {item.target_container[:12]} "
            f"({item.address})"
        )
    for member_id in plan.die:
        print(f"  die       {member_id[:12]}")
    for item in plan.untouched:
        print(f"  untouched {item.member_id[:12]} ({item.reason})")
    print(f"  container (removed last): {plan.container_id[:12]}")

    to_die = [*plan.die, plan.container_id]
    if plan.ledger_root is None:
        print(
            "  ledger not reachable beside the corpus root — run `ath ledger worklist "
            "<id>` yourself for each to-die record above before applying."
        )
        return
    any_claims = False
    for rid in to_die:
        rows = plan.citing_claims.get(rid) or []
        if rows:
            any_claims = True
            print(f"  ledger impact for {rid[:12]}:")
            for row in rows:
                print(f"    {row}")
    if not any_claims:
        print("  ledger impact: no citing claims found for any to-die record.")


def _print_result(result: RetireResult) -> None:
    for item in result.extended:
        print(f"  extended {item.member_id[:12]} -> {item.target_container[:12]}")
    for member_id in result.died:
        print(f"  removed  {member_id[:12]} (die)")
    print(f"  removed  {result.container_removed[:12]} (container)")


def _plan_to_dict(plan: RetirePlan) -> dict[str, Any]:
    return {
        "container": plan.container_id,
        "extend": [
            {
                "member": i.member_id,
                "target_container": i.target_container,
                "address": i.address,
            }
            for i in plan.extend
        ],
        "die": list(plan.die),
        "untouched": [
            {"member": i.member_id, "reason": i.reason} for i in plan.untouched
        ],
        "ledger_reachable": plan.ledger_root is not None,
        "citing_claims": plan.citing_claims,
    }


def _result_to_dict(result: RetireResult) -> dict[str, Any]:
    return {
        "extended": [
            {"member": i.member_id, "target_container": i.target_container}
            for i in result.extended
        ],
        "died": list(result.died),
        "container_removed": result.container_removed,
    }
