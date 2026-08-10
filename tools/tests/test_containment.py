"""The member index + the containment store fallback (spec §2, §12.9).

Exercises the whole containment spine through the real ingest → draft → promote → resolve
pipeline: a raw archive no longer explodes at ingest (one record), its members are indexed by
blake3, and a promoted member's bytes resolve back out of its container by streaming — standalone
residence winning when present, recursing through nested containers, guarding cycles. Health
stops counting a container-resolvable record as missing; `rm` refuses to strand a promoted member.
"""

from __future__ import annotations

import argparse
import shutil
import zipfile
from pathlib import Path

import blake3
import frontmatter
import pytest

from corpus import containment, hashing, health, maintenance, paths, records, resolver, schemas
from corpus._cli import draft as draft_cli
from corpus._cli import ingest as ingest_cli
from corpus._cli import promote as promote_cli
from corpus.store import ArtifactMissing, LocalArtifactStore


def _b3(data: bytes) -> str:
    return blake3.blake3(data).hexdigest()


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults
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
    return hashing.hash_file(archive)["blake3"]


def _draft(root: Path, rid: str) -> None:
    post = records.load(paths.record_path(root, rid))
    draft_cli.derive_record(post, root)
    records.dump(post, paths.record_path(root, rid))


def _ingest_and_draft(root: Path, archive: Path) -> str:
    rid = _ingest(root, archive)
    _draft(root, rid)
    return rid


def _promote(root: Path, uri: str) -> int:
    return promote_cli.run(argparse.Namespace(uri=uri, json=False, corpus_root=str(root)))


# ---------- the zip default flip ---------- #


def test_ingest_no_longer_explodes_a_zip(tmp_path):
    root = _corpus(tmp_path)
    z = _zip(tmp_path / "b.zip", {"a.txt": b"aa", "sub/b.txt": b"bb"})
    rid = _ingest(root, z)
    # ONE record, the container itself — members are NOT ingested as separate records (2.1).
    recs = list(records.iter_record_paths(root))
    assert [r.stem for r in recs] == [rid]
    assert LocalArtifactStore(root).is_local(rid, "zip")  # bytes landed in artifacts/


# ---------- the member index ---------- #


def test_member_index_maps_members_to_container(tmp_path):
    root = _corpus(tmp_path)
    z = _zip(tmp_path / "b.zip", {"a.txt": b"aa", "sub/b.txt": b"bb"})
    cid = _ingest_and_draft(root, z)

    idx = containment.build_member_index(root)
    assert idx[_b3(b"aa")] == [(cid, "path=a.txt")]
    assert idx[_b3(b"bb")] == [(cid, "path=sub/b.txt")]


# ---------- the store fallback ---------- #


def test_promoted_member_resolves_by_streaming(tmp_path):
    root = _corpus(tmp_path)
    payload = b"hello containment world\n"
    z = _zip(tmp_path / "b.zip", {"note.txt": payload})
    cid = _ingest_and_draft(root, z)

    assert _promote(root, f"corpus://{cid}?path=note.txt") == 0
    pid = _b3(payload)
    # No standalone artifact for the promoted record.
    assert not LocalArtifactStore(root).is_local(pid, "txt")

    out = resolver.resolve(f"corpus://{pid}", root)
    assert out.read_bytes() == payload
    assert _b3(out.read_bytes()) == pid  # bytes hash to the id — same bytes, two residences
    # materialized into the resolver cache (not artifacts/), so gc reclaims it by age.
    assert "cache" in out.parts


def test_standalone_residence_wins_over_container(tmp_path):
    root = _corpus(tmp_path)
    payload = b"resident twice\n"
    z = _zip(tmp_path / "b.zip", {"note.txt": payload})
    cid = _ingest_and_draft(root, z)
    _promote(root, f"corpus://{cid}?path=note.txt")
    pid = _b3(payload)

    # Give the promoted record a standalone artifact too; residence-present must win (§2).
    standalone = tmp_path / "note.txt"
    standalone.write_bytes(payload)
    LocalArtifactStore(root).put(pid, "txt", standalone)

    out = containment.ensure_local_bytes(root, pid, "txt")
    assert "artifacts" in out.parts and "cache" not in out.parts


def test_nested_container_recursive_resolution(tmp_path):
    """A promoted member may itself be a container: promote the inner zip, DRAFT it (its bytes
    stream out of the outer zip), promote a member of it, and resolve that member — bytes cross
    two container hops."""
    root = _corpus(tmp_path)
    deep = b"deep member bytes\n"
    inner = _zip(tmp_path / "inner.zip", {"m.txt": deep})
    outer = _zip(tmp_path / "outer.zip", {"inner.zip": inner.read_bytes()})

    outer_id = _ingest_and_draft(root, outer)
    inner_id = _b3(inner.read_bytes())

    # Promote the inner zip out of the outer, then draft it from its containment-resolved bytes.
    assert _promote(root, f"corpus://{outer_id}?path=inner.zip") == 0
    assert not LocalArtifactStore(root).is_local(inner_id, "zip")
    _draft(root, inner_id)

    # The inner draft declared m.txt as a member — now promote and resolve it (two hops down).
    assert _promote(root, f"corpus://{inner_id}?path=m.txt") == 0
    mid = _b3(deep)
    out = resolver.resolve(f"corpus://{mid}", root)
    assert out.read_bytes() == deep
    assert _b3(out.read_bytes()) == mid


def _stub_record(root: Path, rid: str, mime_type: str) -> None:
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "status": "stub", "touch": "corpus.ingest@0"})
    records.set_artifact_block(post, mime=mime_type, fields={})
    records.dump(post, paths.record_path(root, rid))


def test_cycle_guard(tmp_path):
    root = _corpus(tmp_path)
    a, b = "a" * 64, "b" * 64
    _stub_record(root, a, "application/zip")
    _stub_record(root, b, "application/zip")
    cyclic = {a: [(b, "path=x")], b: [(a, "path=y")]}
    with pytest.raises(ArtifactMissing, match="cycle"):
        containment.ensure_local_bytes(root, a, "zip", member_index=cyclic)


def test_unresolvable_bare_id_raises(tmp_path):
    root = _corpus(tmp_path)
    with pytest.raises(ArtifactMissing, match="no standalone file"):
        containment.ensure_local_bytes(root, "f" * 64, "bin", member_index={})


# ---------- health ---------- #


def test_health_promoted_not_missing_but_lost_is(tmp_path):
    root = _corpus(tmp_path)
    payload = b"health check bytes\n"
    z = _zip(tmp_path / "b.zip", {"note.txt": payload})
    cid = _ingest_and_draft(root, z)
    _promote(root, f"corpus://{cid}?path=note.txt")
    pid = _b3(payload)

    # A genuinely lost record: a stub whose bytes were never stored and isn't a container member.
    lost = "c" * 64
    _stub_record(root, lost, "application/pdf")

    refs = health.load_all_records(root)
    missing = health.missing_artifacts(refs, root, skip_remote_check=True)
    missing_ids = {m["id"] for m in missing}
    assert cid not in missing_ids  # standalone present
    assert pid not in missing_ids  # container-resolvable (§12.9), NOT missing
    assert lost in missing_ids  # unresolvable by any route → missing


# ---------- rm container guard ---------- #


def test_rm_refuses_to_strand_a_promoted_member(tmp_path):
    root = _corpus(tmp_path)
    payload = b"do not strand me\n"
    z = _zip(tmp_path / "b.zip", {"note.txt": payload})
    cid = _ingest_and_draft(root, z)
    _promote(root, f"corpus://{cid}?path=note.txt")
    pid = _b3(payload)

    # Only one container holds pid and it has no standalone artifact — removal would strand it,
    # so the dry run names the promoted member and refuses.
    blocked = maintenance.remove_records(root, [cid], execute=True)
    assert cid in blocked.blocked and cid not in blocked.removed
    assert pid in blocked.plans[0].stranded_promoted
    assert not blocked.plans[0].surviving_routes
    assert paths.record_path(root, cid).is_file()  # not removed

    # --force removes anyway (the failure mode is then loud: pid becomes unresolvable).
    forced = maintenance.remove_records(root, [cid], force=True, execute=True)
    assert cid in forced.removed
    assert not paths.record_path(root, cid).is_file()


def test_rm_proceeds_when_another_container_holds_the_member(tmp_path):
    """Route-aware guard (§12.8/§12.17): a promoted member also held by a SECOND container is not
    stranded by removing the first — removal proceeds and the surviving container route is named."""
    root = _corpus(tmp_path)
    payload = b"held by two containers\n"
    # Identical member bytes in two different archives → one promoted id, two container routes.
    z1 = _zip(tmp_path / "one.zip", {"note.txt": payload, "extra1.txt": b"x1"})
    z2 = _zip(tmp_path / "two.zip", {"note.txt": payload, "extra2.txt": b"x2"})
    cid1 = _ingest_and_draft(root, z1)
    cid2 = _ingest_and_draft(root, z2)
    _promote(root, f"corpus://{cid1}?path=note.txt")
    pid = _b3(payload)

    plan = maintenance.plan_removal(root, [cid1])[0]
    assert pid not in plan.stranded_promoted
    assert pid in {m for m, _ in plan.surviving_routes}
    assert any(cid2[:12] in route for _, route in plan.surviving_routes)

    # Not blocked; removal proceeds without --force, and pid still resolves out of cid2.
    result = maintenance.remove_records(root, [cid1], execute=True)
    assert cid1 in result.removed and not result.blocked
    assert not paths.record_path(root, cid1).is_file()
    out = resolver.resolve(f"corpus://{pid}", root)
    assert out.read_bytes() == payload


def test_rm_proceeds_when_member_has_a_standalone_artifact(tmp_path):
    """A promoted member with its own standalone artifact survives its container's removal —
    residence-present is an independent route (§2), so the guard does not block."""
    root = _corpus(tmp_path)
    payload = b"also standalone\n"
    z = _zip(tmp_path / "b.zip", {"note.txt": payload})
    cid = _ingest_and_draft(root, z)
    _promote(root, f"corpus://{cid}?path=note.txt")
    pid = _b3(payload)

    # Give the promoted member a standalone artifact (a `pack`/re-ingest could produce this).
    standalone = tmp_path / "note.txt"
    standalone.write_bytes(payload)
    LocalArtifactStore(root).put(pid, "txt", standalone)

    plan = maintenance.plan_removal(root, [cid])[0]
    assert pid not in plan.stranded_promoted
    assert any(m == pid and "standalone" in route for m, route in plan.surviving_routes)

    result = maintenance.remove_records(root, [cid], execute=True)
    assert cid in result.removed and not result.blocked


# ---------- the self-referential member row (#145) ---------- #


def test_self_referential_member_row_is_not_a_route(tmp_path):
    """A promoted single-member record whose attested roster declares ITSELF (transport ==
    own id — the honest derivation for a one-card vCard, #145) must still resolve through
    its REAL container: a self-row is an identity statement, not a route, and taking it
    used to dead-end in the cycle guard before any real route was tried."""
    root = _corpus(tmp_path)
    card = b"BEGIN:VCARD\nVERSION:3.0\nFN:K\nEND:VCARD\n"
    z = _zip(tmp_path / "b.zip", {"card.vcf": card})
    cid = _ingest_and_draft(root, z)
    member = _b3(card)
    assert _promote(root, f"corpus://{cid}?path=card.vcf") == 0

    # Simulate the contact-card shape op's attested roster: the whole artifact IS card 1.
    p = paths.record_path(root, member)
    post = records.load(p)
    records.append_member(
        post, media_type="text/vcard", address="card=1",
        transport=f"blake3:{member}", fields={"bytes": len(card)},
    )
    records.dump(post, p)

    idx = containment.build_member_index(root)
    assert idx[member] == [(cid, "path=card.vcf")]  # the self-row is excluded outright
    out = containment.ensure_local_bytes(root, member, "vcf", member_index=idx)
    assert out.read_bytes() == card


def test_member_sniff_name_only_trusts_a_path_tail():
    """#149: only a `path=` tail is a filename. Every other scheme addresses a POSITION, and
    handing its tail to `mimetypes` invents a type from a number — an `el=` element path's
    trailing `.3` reads as a man-page section (`application/x-troff-man`)."""
    assert containment.member_sniff_name("path=word/document.xml") == "document.xml"
    assert containment.member_sniff_name("path=report.pdf") == "report.pdf"
    for position in ("el=1.2.2.1.3.3", "msg=7", "part=3", "stream_id=0", "card=2"):
        assert containment.member_sniff_name(position) is None
    # A declared filename always wins, whatever the address names.
    assert containment.member_sniff_name("el=1.2.3", "logo.svg") == "logo.svg"
    # An op chained onto the address makes the whole thing a request, not a member name.
    assert containment.member_sniff_name("path=a.png&bbox=0,0,1,1") is None
