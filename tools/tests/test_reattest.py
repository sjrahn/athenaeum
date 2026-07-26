"""`corpus reattest` (spec §12.4.6, §8.3) — re-derives the attested layer (artifact fields,
the members roster, drafter issues) from the artifact, never touching the authored layer
(content zone, editorial fields). Idempotent: an unchanged record re-derives byte-for-byte and
appends no touch. *(3.4: the roster carries no authored field at all, so nothing is carried
across the strip; a pre-3.4 record still holding member descriptions is refused — §12.26.)*"""

from __future__ import annotations

import zipfile
from pathlib import Path

import frontmatter
import pytest
import yaml

from corpus import derive, hashing, paths, records, schemas
from corpus._cli import reattest as reattest_cli
from corpus.store import LocalArtifactStore


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _ingest_zip(root: Path) -> str:
    src = root / "bundle.zip"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("a/one.txt", "hello one")
        zf.writestr("b/two.txt", "hello two")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "zip", src)
    src.unlink()
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "",
         "transport": f"sha256:{h['sha256']}", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/zip", fields={})
    records.append_origin_block(post, uri=None, snapshot="2026-01-01T00:00:00Z",
                                fields={"filename": "bundle.zip"})
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_reattest_derives_embeds_on_a_stub(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_zip(root)
    rf = paths.record_path(root, rid)

    # A freshly-ingested stub has no embeds yet.
    assert list(records.iter_embed_blocks(records.load(rf))) == []

    new_text = reattest_cli.reattest_record(rf, root)
    rf.write_text(new_text, encoding="utf-8")
    post = records.load(rf)

    embeds = list(records.iter_embed_blocks(post))
    assert len(embeds) == 2  # the zip's two members, attested
    assert {e["address"] for e in embeds} == {"path=a/one.txt", "path=b/two.txt"}
    assert not records.has_editorial_override(post)  # attestation never authors the vouch
    assert records.derived_state(post) == "proxy"  # embeds don't count as a stored rendering
    assert (post.content or "") == ""          # a manifest has no body
    # a touch was appended for the real change
    touch = post.metadata["touch"]
    chain = touch if isinstance(touch, list) else [touch]
    assert any("attest" in t for t in chain)


def test_reattest_is_idempotent(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_zip(root)
    rf = paths.record_path(root, rid)

    first = reattest_cli.reattest_record(rf, root)
    rf.write_text(first, encoding="utf-8")
    # A second re-attest re-derives byte-for-byte → no change, no new touch.
    second = reattest_cli.reattest_record(rf, root)
    assert second == first


def test_reattest_preserves_authored_layer(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_zip(root)
    rf = paths.record_path(root, rid)
    # Attest, then simulate normalize: author an embed description + editorial fields + body.
    rf.write_text(reattest_cli.reattest_record(rf, root), encoding="utf-8")
    post = records.load(rf)
    post.metadata["title"] = "My Bundle"
    post.metadata["description"] = "An authored summary."
    post.content = (
        "<!--segment text\naddress: path=a/one.txt\n"
        "description: the first member, described\n-->\n\nauthored body\n"
    )
    records.dump(post, rf)

    # Re-attest must NOT clobber the authored layer.
    new_text = reattest_cli.reattest_record(rf, root)
    rf.write_text(new_text, encoding="utf-8")
    after = records.load(rf)
    assert after.metadata["title"] == "My Bundle"
    assert after.metadata["description"] == "An authored summary."
    assert "authored body" in (after.content or "")
    # *(3.4)* A member's narration lives on the block that PLACES it, which is in the content
    # zone — so re-attestation cannot touch it. That is the point of moving it there: the
    # pre-3.4 home was inside the attested roster, carried across the strip by transport hash,
    # which lost the text outright whenever the member itself had been pruned (§12.26).
    assert "the first member, described" in (after.content or "")


def test_members_roster_cannot_hold_a_description(tmp_path):
    """The roster is closed to four keys (spec §4.3.1.4), enforced at the emitter.

    A caller handing over a `description` gets it dropped rather than written, so no producer
    can widen the block by passing extra fields — the closed shape holds without every drafter
    having to know about it."""
    root = _make_corpus(tmp_path)
    rid = _ingest_zip(root)
    rf = paths.record_path(root, rid)
    rf.write_text(reattest_cli.reattest_record(rf, root), encoding="utf-8")

    post = records.load(rf)
    post.metadata["_embeds"][0]["fields"]["description"] = "not a home for this"
    records.dump(post, rf)

    text = rf.read_text(encoding="utf-8")
    assert "<!--members" in text
    assert "not a home for this" not in text
    after = records.load(rf)
    assert (after.metadata["_embeds"][0].get("fields") or {}).get("description") is None
    # Nothing is pending: the record is already 3.4, so there is no legacy text to re-home.
    assert records.pending_member_descriptions(after) == []


def test_reattest_refuses_a_legacy_record_with_authored_descriptions(tmp_path):
    """The migration's safety property (§12.26): re-attestation rebuilds the roster wholesale,
    so a pre-3.4 record whose per-asset blocks still carry authored prose must be refused rather
    than converted — otherwise the text is destroyed by an operation nobody asked to be
    destructive. The same shape of defect as §12.25's: a correct operation performed before a
    cheap check."""
    root = _make_corpus(tmp_path)
    rid = _ingest_zip(root)
    rf = paths.record_path(root, rid)
    rf.write_text(reattest_cli.reattest_record(rf, root), encoding="utf-8")

    # Rewrite the roster in the LEGACY per-asset form, carrying a description.
    post = records.load(rf)
    post.metadata["_members_block"] = False
    post.metadata["_embeds"][0]["fields"]["description"] = "the first member, described"
    records.dump(post, rf)
    assert "<!--embed " in rf.read_text(encoding="utf-8")

    legacy = records.load(rf)
    assert records.pending_member_descriptions(legacy) == [
        ("path=a/one.txt", "the first member, described")
    ]

    with pytest.raises(derive.PendingMemberDescriptions) as exc:
        reattest_cli.reattest_record(rf, root)
    assert "path=a/one.txt" in str(exc.value)
    # And the record on disk is untouched — a refusal that had already written would be no gate.
    assert "the first member, described" in rf.read_text(encoding="utf-8")

    # The deliberate override converts and drops, for members with no content zone to move to.
    post = records.load(rf)
    derive.attest(post, root, strip=True, discard_member_descriptions=True)
    records.dump(post, rf)
    text = rf.read_text(encoding="utf-8")
    assert "<!--members" in text
    assert "the first member, described" not in text


def _write_origin_overlay(root: Path, filename: str, applies_to: dict) -> None:
    d = root / "schema" / "origin" / "web"
    d.mkdir(parents=True, exist_ok=True)
    (d / filename).write_text(
        yaml.safe_dump({"applies_to": applies_to}, sort_keys=False), encoding="utf-8"
    )
    schemas.cache_clear()


def _ingest_zip_with_uri(root: Path, uri: str) -> str:
    src = root / "bundle.zip"
    with zipfile.ZipFile(src, "w") as zf:
        zf.writestr("a/one.txt", "hello one")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "zip", src)
    src.unlink()
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "title": "", "description": "",
         "transport": f"sha256:{h['sha256']}", "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="application/zip", fields={})
    records.append_origin_block(post, uri=uri, snapshot="2026-01-01T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))
    return rid


def test_reattest_qualifies_bare_origin_block_with_matching_overlay(tmp_path):
    """§7.2's origin-block host qualification is wired into `corpus reattest` (the shared
    `derive.apply_drafter_result` seam) — a record ingested before an overlay existed, or
    before this fix, gets its bare origin block qualified on its next re-attest."""
    root = _make_corpus(tmp_path)
    _write_origin_overlay(
        root, "video.example.yaml",
        {"host_patterns": ["video.example"], "include_subdomains": True},
    )
    rid = _ingest_zip_with_uri(root, "https://video.example/v/1")
    rf = paths.record_path(root, rid)

    # bare at birth
    assert next(iter(records.iter_origin_blocks(records.load(rf))))["id"] is None

    new_text = reattest_cli.reattest_record(rf, root)
    rf.write_text(new_text, encoding="utf-8")
    post = records.load(rf)
    origins = list(records.iter_origin_blocks(post))
    assert origins[0]["id"] == "video.example"
    assert "<!--origin video.example" in rf.read_text(encoding="utf-8")
    assert "<!--origin\n" not in rf.read_text(encoding="utf-8")  # opener upgraded, not left bare


def test_reattest_never_downgrades_a_producer_declared_origin_id(tmp_path):
    """A producer-declared id is sacrosanct — re-attest must never re-stamp or downgrade it,
    even when a DIFFERENT overlay's host pattern would also match the block's uri."""
    root = _make_corpus(tmp_path)
    _write_origin_overlay(root, "other.example.yaml", {"host_pattern": "video.example"})
    rid = _ingest_zip_with_uri(root, "https://video.example/v/1")
    rf = paths.record_path(root, rid)
    post = records.load(rf)
    assert records.set_origin_schema_id(post, "producer-declared") is True
    records.dump(post, rf)

    new_text = reattest_cli.reattest_record(rf, root)
    rf.write_text(new_text, encoding="utf-8")
    post = records.load(rf)
    assert next(iter(records.iter_origin_blocks(post)))["id"] == "producer-declared"


def test_reattest_origin_qualification_is_idempotent(tmp_path):
    root = _make_corpus(tmp_path)
    _write_origin_overlay(root, "video.example.yaml", {"host_pattern": "video.example"})
    rid = _ingest_zip_with_uri(root, "https://video.example/v/1")
    rf = paths.record_path(root, rid)

    first = reattest_cli.reattest_record(rf, root)
    rf.write_text(first, encoding="utf-8")
    assert next(iter(records.iter_origin_blocks(records.load(rf))))["id"] == "video.example"
    # A second re-attest re-derives byte-for-byte — nothing left to qualify.
    second = reattest_cli.reattest_record(rf, root)
    assert second == first


def test_reattest_cli_dry_run_writes_nothing(tmp_path):
    root = _make_corpus(tmp_path)
    _ingest_zip(root)

    class _Args:
        target = None
        mime = None
        host = None
        state = "any"
        dry_run = True
        fingerprint = None
        corpus_root = str(root)

    before = {p: p.read_text() for p in records.iter_record_paths(root)}
    rc = reattest_cli.run(_Args())
    assert rc == 0
    after = {p: p.read_text() for p in records.iter_record_paths(root)}
    assert before == after  # dry run mutated nothing
