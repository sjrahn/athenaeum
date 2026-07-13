"""`corpus redraft` — deterministic, idempotent bulk re-derive."""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import hashing, paths, records, schemas
from corpus._cli import draft as draft_cli
from corpus._cli import redraft as redraft_cli
from corpus.store import LocalArtifactStore


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _ingest_html(root: Path, html: str, *, name: str = "page") -> str:
    src = root / f"{name}.html"
    src.write_text(html, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    # Build the stub via the canonical frontmatter helper (as ingest / re-stub do) so a
    # re-derive — which rebuilds the stub the same way — round-trips byte-identically.
    fm = records.stub_frontmatter(
        record_id=rid,
        transport=f"sha256:{h['sha256']}",
        touch_id="corpus.ingest@0.1.0",
        description="",
    )
    post = frontmatter.Post("", **fm)
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri=f"https://x.test/{name}", snapshot="2026-06-03T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))
    return rid


def _draft(root: Path, rid: str) -> Path:
    rf = paths.record_path(root, rid)
    post = records.load(rf)
    draft_cli.derive_record(post, root)
    records.dump(post, rf)
    return rf


class _Args:
    """A hand-built args namespace for `redraft.run` (no argparse)."""

    def __init__(self, root: Path, **kw):
        self.target = None
        self.mime = None
        self.host = None
        # 3.0: a re-derived mechanical body leaves the record a `stub` (§12.18 step 3), so the
        # transitional redraft tests target every status — the old `draft` default matched none.
        self.status = "any"
        self.force = False
        self.dry_run = False
        self.fingerprint = None
        self.corpus_root = str(root)
        self.__dict__.update(kw)


def test_redraft_is_idempotent(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_html(root, "<html><body><p>hello world words</p></body></html>")
    rf = _draft(root, rid)
    before = rf.read_text(encoding="utf-8")
    # Re-deriving a correctly-drafted record produces byte-identical output → no write.
    redraft_cli.run(_Args(root))
    assert rf.read_text(encoding="utf-8") == before


def test_redraft_surfaces_a_knob_flip(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_html(root, "<html><body><p>some words for a fingerprint</p></body></html>")
    rf = _draft(root, rid)
    assert "perceptual:" not in rf.read_text(encoding="utf-8")  # fingerprinting off by default
    # Flip it on and re-derive → exactly this record gains a perceptual.
    redraft_cli.run(_Args(root, fingerprint=True))
    assert "perceptual: simhash:" in rf.read_text(encoding="utf-8")


def test_redraft_dry_run_writes_nothing(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_html(root, "<html><body><p>dry run words here</p></body></html>")
    rf = _draft(root, rid)
    before = rf.read_text(encoding="utf-8")
    redraft_cli.run(_Args(root, fingerprint=True, dry_run=True))
    assert rf.read_text(encoding="utf-8") == before  # would change, but --dry-run writes nothing


def test_redraft_protects_normalized_without_force(tmp_path):
    root = _make_corpus(tmp_path)
    rid = _ingest_html(root, "<html><body><p>normalized words here</p></body></html>")
    rf = _draft(root, rid)
    post = records.load(rf)
    post.metadata["status"] = "normalized"
    records.dump(post, rf)
    before = rf.read_text(encoding="utf-8")

    # --status any without --force must NOT touch a normalized record.
    redraft_cli.run(_Args(root, status="any", fingerprint=True))
    assert rf.read_text(encoding="utf-8") == before

    # --force re-derives it (status returns to stub; normalization discarded).
    redraft_cli.run(_Args(root, status="any", force=True, fingerprint=True))
    assert records.load(rf).metadata["status"] == "stub"
