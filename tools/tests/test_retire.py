"""Container retirement — `corpus retire` (spec §12.8, v37 owner ruling): every promoted
member of a retiring container resolves in exactly one of two ways, decided by bytes —
extend (a live route via `corpus promote`'s §8.1 fold) or die (removed with the
container, the `corpus rm` per-record machinery) — manifest-first (dry-run by default),
zero partial states on an extend-fold failure, and the ledger-impact disclosure for
every to-die record via `ath ledger worklist` when a ledger root sits beside the corpus
root (the instance layout).
"""

from __future__ import annotations

import argparse
import json
import shutil
import zipfile
from pathlib import Path

import blake3
import pytest

from corpus import paths, records, resolver, schemas
from corpus._cli import dispatch, retire
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _zip(path: Path, members: dict[str, bytes]) -> Path:
    with zipfile.ZipFile(path, "w") as zf:
        for name, data in members.items():
            zf.writestr(name, data)
    return path


def _ingest(root: Path, archive: Path) -> str:
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / archive.name
    shutil.copy(archive, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    from corpus import hashing

    return hashing.hash_file(archive)["blake3"]


def _draft(root: Path, rid: str) -> None:
    from corpus._cli import draft as draft_cli

    post = records.load(paths.record_path(root, rid))
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, rid))


def _ingest_and_draft(root: Path, archive: Path) -> str:
    rid = _ingest(root, archive)
    _draft(root, rid)
    return rid


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


# ---------- extend ---------- #


def test_retire_extends_when_another_live_container_holds_the_bytes(tmp_path):
    root = _corpus(tmp_path)
    payload = b"held by two containers\n"
    z1 = _zip(tmp_path / "one.zip", {"shared.txt": payload, "extra1.txt": b"x1"})
    z2 = _zip(tmp_path / "two.zip", {"shared.txt": payload, "extra2.txt": b"x2"})
    cid1 = _ingest_and_draft(root, z1)
    cid2 = _ingest_and_draft(root, z2)
    assert _promote(root, f"corpus://{cid1}?path=shared.txt") == 0
    pid = _b3(payload)

    plan = retire.plan_retirement(root, cid1)
    assert plan.die == []
    assert len(plan.extend) == 1
    assert plan.extend[0].member_id == pid
    assert plan.extend[0].target_container == cid2
    assert plan.extend[0].address == "path=shared.txt"

    result = retire.execute_retirement(root, plan)
    assert result.container_removed == cid1
    assert result.died == []
    assert [i.member_id for i in result.extended] == [pid]

    # Container gone; member survives with a LIVE route through cid2.
    assert not paths.record_path(root, cid1).is_file()
    assert paths.record_path(root, pid).is_file()
    out = resolver.resolve(f"corpus://{pid}", root)
    assert out.read_bytes() == payload

    # Retired route preserved as history; the fresh fold is the latest origin block.
    post = records.load(paths.record_path(root, pid))
    uris = list(records.iter_origin_uris(post))
    assert uris == [f"corpus://{cid1}?path=shared.txt", f"corpus://{cid2}?path=shared.txt"]


def test_retire_already_promoted_elsewhere_is_untouched_not_reextended(tmp_path):
    """The member is ALREADY promoted under the live container too (a prior manual
    promote) — its OWN origin lineage already shows a live route via cid2, so it's
    UNTOUCHED (no redundant fold), not routed through `extend` again."""
    root = _corpus(tmp_path)
    payload = b"already folded\n"
    z1 = _zip(tmp_path / "one.zip", {"shared.txt": payload, "extra1.txt": b"x1"})
    z2 = _zip(tmp_path / "two.zip", {"shared.txt": payload, "extra2.txt": b"x2"})
    cid1 = _ingest_and_draft(root, z1)
    cid2 = _ingest_and_draft(root, z2)
    assert _promote(root, f"corpus://{cid1}?path=shared.txt") == 0
    assert _promote(root, f"corpus://{cid2}?path=shared.txt") == 0
    pid = _b3(payload)

    plan = retire.plan_retirement(root, cid1)
    assert plan.extend == []
    assert plan.die == []
    assert [i.member_id for i in plan.untouched] == [pid]
    assert "live containment route" in plan.untouched[0].reason
    assert cid2[:12] in plan.untouched[0].reason

    result = retire.execute_retirement(root, plan)
    assert result.container_removed == cid1
    assert result.extended == []
    assert paths.record_path(root, pid).is_file()
    post = records.load(paths.record_path(root, pid))
    uris = list(records.iter_origin_uris(post))
    assert uris == [f"corpus://{cid1}?path=shared.txt", f"corpus://{cid2}?path=shared.txt"]


def test_retire_untouched_via_independent_producer_origin(tmp_path):
    """A member whose bytes are the SAME as a container's embed, but whose record was
    minted by a genuine standalone ingest (a real producer/capture origin, never
    `corpus promote`), is untouched — this retirement never kept it alive."""
    root = _corpus(tmp_path)
    payload = b"<html>independently captured</html>\n"
    standalone_src = tmp_path / "standalone.html"
    standalone_src.write_bytes(payload)
    pid = _ingest(root, standalone_src)  # a genuine standalone ingest — no containment uri

    z = _zip(tmp_path / "b.zip", {"note.html": payload, "other.txt": b"unrelated\n"})
    cid = _ingest_and_draft(root, z)
    # No promote call: `pid`'s record already exists (content-addressed, same bytes) —
    # it's still one of the container's "promoted member records" by the guard's own
    # definition (a record exists at that hash), even though promote never touched it.
    assert pid == _b3(payload)

    plan = retire.plan_retirement(root, cid)
    assert plan.extend == []
    assert plan.die == []
    assert [i.member_id for i in plan.untouched] == [pid]
    assert "independent capture origin" in plan.untouched[0].reason

    result = retire.execute_retirement(root, plan)
    assert result.container_removed == cid
    assert paths.record_path(root, pid).is_file()


# ---------- die ---------- #


def test_retire_dies_when_no_live_container_holds_the_bytes(tmp_path):
    root = _corpus(tmp_path)
    payload = b"do not strand me\n"
    z = _zip(tmp_path / "b.zip", {"note.txt": payload})
    cid = _ingest_and_draft(root, z)
    assert _promote(root, f"corpus://{cid}?path=note.txt") == 0
    pid = _b3(payload)

    plan = retire.plan_retirement(root, cid)
    assert plan.extend == []
    assert plan.die == [pid]

    result = retire.execute_retirement(root, plan)
    assert result.died == [pid]
    assert result.container_removed == cid
    assert not paths.record_path(root, cid).is_file()
    assert not paths.record_path(root, pid).is_file()


def test_retire_dies_even_with_a_materialized_standalone_artifact(tmp_path):
    """Custody is not provenance (spec §12.8, v37 owner ruling): an operator resolving
    a promoted member's bytes into `artifacts/` (e.g. `corpus resolve` + a manual copy)
    does NOT make the member survive — its origin lineage runs ONLY through the
    retiring container, so with no other live container it dies strictly, artifact
    included. This is the exact real-world case the ruling was written for (153
    manually-materialized stranded records that had to die with their monolith)."""
    root = _corpus(tmp_path)
    payload = b"squirreled away, but still only origin-linked to cid\n"
    z = _zip(tmp_path / "b.zip", {"note.txt": payload})
    cid = _ingest_and_draft(root, z)
    assert _promote(root, f"corpus://{cid}?path=note.txt") == 0
    pid = _b3(payload)

    from corpus.store import LocalArtifactStore

    standalone = tmp_path / "note.txt"
    standalone.write_bytes(payload)
    LocalArtifactStore(root).put(pid, "txt", standalone)
    assert LocalArtifactStore(root).is_local(pid, "txt")

    plan = retire.plan_retirement(root, cid)
    assert plan.untouched == []
    assert plan.extend == []
    assert plan.die == [pid]

    result = retire.execute_retirement(root, plan)
    assert result.died == [pid]
    assert result.container_removed == cid
    assert not paths.record_path(root, pid).is_file()  # record gone
    assert not LocalArtifactStore(root).is_local(pid, "txt")  # artifact deleted too


# ---------- mixed ---------- #


def test_retire_mixed_extend_and_die_in_one_sweep(tmp_path):
    root = _corpus(tmp_path)
    shared = b"shared bytes\n"
    solo = b"only here\n"
    z1 = _zip(tmp_path / "one.zip", {"shared.txt": shared, "solo.txt": solo})
    z2 = _zip(tmp_path / "two.zip", {"shared.txt": shared})
    cid1 = _ingest_and_draft(root, z1)
    cid2 = _ingest_and_draft(root, z2)
    assert _promote(root, f"corpus://{cid1}?path=shared.txt") == 0
    assert _promote(root, f"corpus://{cid1}?path=solo.txt") == 0
    shared_id = _b3(shared)
    solo_id = _b3(solo)

    plan = retire.plan_retirement(root, cid1)
    assert [i.member_id for i in plan.extend] == [shared_id]
    assert plan.die == [solo_id]

    result = retire.execute_retirement(root, plan)
    assert [i.member_id for i in result.extended] == [shared_id]
    assert result.died == [solo_id]
    assert not paths.record_path(root, cid1).is_file()
    assert paths.record_path(root, shared_id).is_file()
    assert not paths.record_path(root, solo_id).is_file()
    assert paths.record_path(root, cid2).is_file()  # the live container, untouched


def test_retire_no_promoted_members_removes_container_clean(tmp_path):
    root = _corpus(tmp_path)
    z = _zip(tmp_path / "b.zip", {"note.txt": b"never promoted\n"})
    cid = _ingest_and_draft(root, z)

    plan = retire.plan_retirement(root, cid)
    assert plan.extend == [] and plan.die == []

    result = retire.execute_retirement(root, plan)
    assert result.container_removed == cid
    assert not paths.record_path(root, cid).is_file()


# ---------- dry-run / CLI wiring ---------- #


def test_retire_dry_run_touches_nothing(tmp_path):
    root = _corpus(tmp_path)
    payload = b"untouched by a dry run\n"
    z = _zip(tmp_path / "b.zip", {"note.txt": payload})
    cid = _ingest_and_draft(root, z)
    assert _promote(root, f"corpus://{cid}?path=note.txt") == 0
    pid = _b3(payload)

    before = {p: p.read_bytes() for p in (root / "records").rglob("*.md")}
    assert dispatch(["retire", cid, "--corpus-root", str(root)]) == 0
    after = {p: p.read_bytes() for p in (root / "records").rglob("*.md")}
    assert before == after
    assert paths.record_path(root, cid).is_file()
    assert paths.record_path(root, pid).is_file()


def test_retire_apply_via_cli_executes(tmp_path):
    root = _corpus(tmp_path)
    payload = b"apply for real\n"
    z = _zip(tmp_path / "b.zip", {"note.txt": payload})
    cid = _ingest_and_draft(root, z)
    assert _promote(root, f"corpus://{cid}?path=note.txt") == 0
    pid = _b3(payload)

    assert dispatch(["retire", cid, "--apply", "--corpus-root", str(root)]) == 0
    assert not paths.record_path(root, cid).is_file()
    assert not paths.record_path(root, pid).is_file()  # no other route → died


# ---------- abort-on-fold-failure ---------- #


def test_retire_aborts_before_any_removal_on_extend_fold_failure(tmp_path):
    root = _corpus(tmp_path)
    shared = b"shared bytes\n"
    solo = b"only here\n"
    z1 = _zip(tmp_path / "one.zip", {"shared.txt": shared, "solo.txt": solo})
    z2 = _zip(tmp_path / "two.zip", {"shared.txt": shared})
    cid1 = _ingest_and_draft(root, z1)
    cid2 = _ingest_and_draft(root, z2)
    assert _promote(root, f"corpus://{cid1}?path=shared.txt") == 0
    assert _promote(root, f"corpus://{cid1}?path=solo.txt") == 0
    shared_id = _b3(shared)
    solo_id = _b3(solo)

    plan = retire.plan_retirement(root, cid1)
    assert len(plan.extend) == 1
    assert plan.die == [solo_id]

    # Corrupt cid2's embed transport hash AFTER planning — the extend-fold's own §8.1
    # blake3 verification will now fail.
    cid2_path = paths.record_path(root, cid2)
    post = records.load(cid2_path)
    for embed in records.iter_embed_blocks(post):
        if embed.get("address") == "path=shared.txt":
            embed["transport"] = "blake3:" + "0" * 64
    records.dump(post, cid2_path)

    with pytest.raises(retire.RetireError):
        retire.execute_retirement(root, plan)

    # ZERO partial states: nothing removed — the die candidate, the extend candidate,
    # and the container itself are all exactly as they were.
    assert paths.record_path(root, cid1).is_file()
    assert paths.record_path(root, cid2).is_file()
    assert paths.record_path(root, shared_id).is_file()
    assert paths.record_path(root, solo_id).is_file()


# ---------- ledger-impact disclosure ---------- #


def test_retire_plan_discloses_ledger_impact_for_to_die_records(tmp_path):
    root = _corpus(tmp_path)
    payload = b"cited by a claim\n"
    z = _zip(tmp_path / "b.zip", {"note.txt": payload})
    cid = _ingest_and_draft(root, z)
    assert _promote(root, f"corpus://{cid}?path=note.txt") == 0
    pid = _b3(payload)

    ledger_root = tmp_path / "ledger"
    (ledger_root / "facts" / "person").mkdir(parents=True)
    (ledger_root / "interpretations").mkdir()
    (ledger_root / "facts" / "person" / "mom.json").write_text(
        json.dumps(
            {
                "id": "mom",
                "type": "person",
                "name": "Mom",
                "sources": {"s1": {"record": pid}},
                "claims": [
                    {
                        "id": "mom:note",
                        "predicate": "wrote",
                        "object": "note",
                        "status": "provisional",
                        "asof": "2026-01-01",
                        "evidence": [{"source": "s1", "kind": "direct"}],
                    }
                ],
            }
        )
    )

    plan = retire.plan_retirement(root, cid)
    assert plan.die == [pid]
    assert plan.ledger_root == ledger_root
    rows = plan.citing_claims[pid]
    assert rows is not None
    assert any("mom:note" in r for r in rows)
    assert plan.citing_claims[cid] == []  # container itself: reachable, no citers


def test_retire_plan_reports_ledger_unreachable(tmp_path):
    root = _corpus(tmp_path)
    z = _zip(tmp_path / "b.zip", {"note.txt": b"no ledger nearby\n"})
    cid = _ingest_and_draft(root, z)

    plan = retire.plan_retirement(root, cid)
    assert plan.ledger_root is None
    assert plan.citing_claims[cid] is None
