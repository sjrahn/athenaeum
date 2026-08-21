"""Derived-data hygiene + deliberate record removal — `corpus gc` / `rm` / `forget-origin`
(corpus/maintenance.py) and the `capture --force --replace` supersession ergonomic.

All offline over a tmp corpus: gc's per-category age-gated sweep (cache / staging / orphan
artifacts / export) and dry-run, rm's plan / ref-check / keep-artifact / empty-shard cleanup,
forget-origin's alias surgery, and replace with `capture_and_ingest` faked.
"""

from __future__ import annotations

import json
import time
from pathlib import Path

import frontmatter
import pytest

from corpus import maintenance, paths, records
from corpus._cli import dispatch
from corpus.store import LocalArtifactStore

ID_A = "aa" * 32
ID_B = "bb" * 32
ID_C = "cc" * 32
ORPHAN_ID = "ee" * 32

URL_A = "https://shop.test/product/a"
URL_B = "https://shop.test/product/b"


# ---------- fixtures ---------- #


def _corpus(tmp_path: Path, name: str = "c") -> Path:
    root = tmp_path / name
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _record(
    root: Path,
    rid: str,
    *,
    uri="https://x.test/" ,
    ext: str = "html",
    mime: str = "text/html",
    body: bytes = b"<html>x</html>",
    contexts: list[dict] | None = None,
) -> frontmatter.Post:
    """A record with its content-addressed artifact on disk."""
    src = root / f"_src_{rid[:8]}.{ext}"
    src.write_bytes(body)
    LocalArtifactStore(root).put(rid, ext, src)
    src.unlink()
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime=mime, fields={})
    records.append_origin_block(post, uri=uri, snapshot="2026-06-04T00:00:00Z")
    for ctx in contexts or []:
        records.append_context_block(
            post,
            namespace=ctx["namespace"],
            id=ctx["id"],
            subtype=ctx.get("subtype"),
            fields=ctx.get("fields") or {},
        )
    records.dump(post, paths.record_path(root, rid))
    return post


def _age(path: Path, days: float) -> None:
    """Backdate a file's mtime by `days` so the age gate considers it prunable."""
    old = time.time() - days * 86400
    import os

    os.utime(path, (old, old))


def _mkfile(path: Path, content: bytes = b"data", *, age_days: float | None = None) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    if age_days is not None:
        _age(path, age_days)
    return path


# ---------- gc / sweep: cache, staging, export ---------- #


def test_sweep_dry_run_lists_without_deleting(tmp_path):
    root = _corpus(tmp_path)
    f = _mkfile(root / "cache" / "ab" / "x.png", age_days=30)
    result = maintenance.sweep(root, older_than_days=7, dry_run=True)
    assert [i.path for i in result.items] == ["cache/ab/x.png"]
    assert result.total_size == f.stat().st_size
    assert f.exists()  # dry run deleted nothing


def test_sweep_executes_and_tidies_empty_shard(tmp_path):
    root = _corpus(tmp_path)
    f = _mkfile(root / "cache" / "ab" / "x.png", age_days=30)
    result = maintenance.sweep(root, older_than_days=7, dry_run=False)
    assert result.dry_run is False
    assert not f.exists()
    assert not (root / "cache" / "ab").exists()  # now-empty shard dir tidied


def test_sweep_age_gate_keeps_fresh(tmp_path):
    root = _corpus(tmp_path)
    old = _mkfile(root / "cache" / "ab" / "old.png", age_days=30)
    fresh = _mkfile(root / "cache" / "cd" / "fresh.png")  # mtime ~ now
    result = maintenance.sweep(root, older_than_days=7, dry_run=False)
    assert not old.exists()
    assert fresh.exists()
    assert [i.path for i in result.items] == ["cache/ab/old.png"]


def test_sweep_older_than_zero_prunes_all(tmp_path):
    root = _corpus(tmp_path)
    fresh = _mkfile(root / "cache" / "ab" / "fresh.png")
    maintenance.sweep(root, older_than_days=0, dry_run=False)
    assert not fresh.exists()


def test_sweep_staging_and_export(tmp_path):
    root = _corpus(tmp_path)
    _mkfile(root / "capture" / "leftover.info.json", age_days=30)
    _mkfile(root / "export" / "bundle.zip", age_days=30)
    result = maintenance.sweep(root, older_than_days=7, dry_run=False)
    cats = {i.category for i in result.items}
    assert cats == {"staging", "export"}


def test_sweep_include_filter(tmp_path):
    root = _corpus(tmp_path)
    _mkfile(root / "cache" / "ab" / "x.png", age_days=30)
    staging = _mkfile(root / "capture" / "y.json", age_days=30)
    result = maintenance.sweep(root, include=["cache"], older_than_days=7, dry_run=False)
    assert result.categories == ("cache",)
    assert staging.exists()  # staging not swept


def test_sweep_unknown_category_raises(tmp_path):
    root = _corpus(tmp_path)
    with pytest.raises(ValueError, match="unknown gc category"):
        maintenance.sweep(root, include=["bogus"])


def test_sweep_empty_corpus_no_crash(tmp_path):
    root = _corpus(tmp_path)
    result = maintenance.sweep(root, dry_run=False)
    assert result.items == []
    assert result.total_size == 0


# ---------- gc / sweep: cache excludes persistent derived indexes by name (§12.8, v21) ---------- #


def _persistent_index_tree(root: Path) -> dict[str, Path]:
    """A cache/ tree with the persistent derived indexes (all old enough to be swept by
    age alone) plus one ordinary cache entry."""
    return {
        "hashes_db": _mkfile(root / "cache" / "hashes.db", age_days=30),
        "hashes_wal": _mkfile(root / "cache" / "hashes.db-wal", age_days=30),
        "hashes_shm": _mkfile(root / "cache" / "hashes.db-shm", age_days=30),
        "locations_db": _mkfile(root / "cache" / "locations.db", age_days=30),
        "locations_wal": _mkfile(root / "cache" / "locations.db-wal", age_days=30),
        "locations_shm": _mkfile(root / "cache" / "locations.db-shm", age_days=30),
        "refidx": _mkfile(root / "cache" / "refidx" / "aa62.sqlite", age_days=30),
        "ordinary": _mkfile(root / "cache" / "ab" / "abcd.txt", age_days=30),
    }


def test_sweep_dry_run_excludes_persistent_indexes(tmp_path):
    root = _corpus(tmp_path)
    files = _persistent_index_tree(root)
    result = maintenance.sweep(root, older_than_days=0, dry_run=True)
    assert [i.path for i in result.items] == ["cache/ab/abcd.txt"]
    for key, f in files.items():
        assert f.exists(), f"dry run must not touch {key}"


def test_sweep_deletes_ordinary_keeps_persistent_indexes(tmp_path):
    root = _corpus(tmp_path)
    files = _persistent_index_tree(root)
    result = maintenance.sweep(root, older_than_days=0, dry_run=False)
    assert [i.path for i in result.items] == ["cache/ab/abcd.txt"]
    assert not files["ordinary"].exists()
    for key in (
        "hashes_db",
        "hashes_wal",
        "hashes_shm",
        "locations_db",
        "locations_wal",
        "locations_shm",
        "refidx",
    ):
        assert files[key].exists(), f"real sweep must keep {key}"


def test_sweep_staging_export_unaffected_by_cache_exclusions(tmp_path):
    root = _corpus(tmp_path)
    _persistent_index_tree(root)
    staging = _mkfile(root / "capture" / "leftover.info.json", age_days=30)
    export = _mkfile(root / "export" / "bundle.zip", age_days=30)
    result = maintenance.sweep(
        root, include=["staging", "export"], older_than_days=7, dry_run=False
    )
    cats = {i.category for i in result.items}
    assert cats == {"staging", "export"}
    assert not staging.exists()
    assert not export.exists()


# ---------- gc / sweep: orphan artifacts ---------- #


def test_sweep_orphans_only_unowned(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A)  # owned artifact at artifacts/aa/<ID_A>.html
    _mkfile(root / "artifacts" / "ee" / f"{ORPHAN_ID}.pdf", age_days=30)  # no record
    result = maintenance.sweep(root, include=["orphans"], older_than_days=7, dry_run=False)
    assert [i.path for i in result.items] == [f"artifacts/ee/{ORPHAN_ID}.pdf"]
    assert paths.artifact_path(root, ID_A, "html").exists()  # owned artifact untouched
    assert not (root / "artifacts" / "ee").exists()


def test_sweep_orphans_age_gated(tmp_path):
    root = _corpus(tmp_path)
    fresh_orphan = _mkfile(root / "artifacts" / "ee" / f"{ORPHAN_ID}.pdf")  # ~ now
    result = maintenance.sweep(root, include=["orphans"], older_than_days=7, dry_run=False)
    assert result.items == []
    assert fresh_orphan.exists()  # young orphan protected (ingest write→record window)


# ---------- gc CLI ---------- #


def test_gc_cli_preview_then_yes(tmp_path, capsys):
    root = _corpus(tmp_path)
    f = _mkfile(root / "cache" / "ab" / "x.png", age_days=30)
    rc = dispatch(["gc", "--corpus-root", str(root)])
    assert rc == 0
    assert "preview" in capsys.readouterr().out
    assert f.exists()
    rc = dispatch(["gc", "--yes", "--corpus-root", str(root)])
    assert rc == 0
    assert "reclaimed" in capsys.readouterr().out
    assert not f.exists()


def test_gc_cli_json(tmp_path, capsys):
    root = _corpus(tmp_path)
    _mkfile(root / "cache" / "ab" / "x.png", age_days=30)
    rc = dispatch(["gc", "--json", "--corpus-root", str(root)])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["dry_run"] is True
    assert payload["categories"]["cache"]["count"] == 1


# ---------- rm: plan + removal ---------- #


def test_gc_cli_empty_include_sweeps_nothing(tmp_path):
    # `corpus gc --include ""` must scope to NOTHING — not fall through to all categories.
    # Regression: the CLI's falsy `if args.include` treated "" as "not provided" → swept all.
    root = _corpus(tmp_path)
    f = _mkfile(root / "cache" / "ab" / "x.png", age_days=30)
    rc = dispatch(["gc", "--include", "", "--yes", "--corpus-root", str(root)])
    assert rc == 0
    assert f.exists()  # empty include sweeps nothing, so the cache file survives


def test_plan_removal_reports_paths_and_size(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A, body=b"x" * 500)
    [plan] = maintenance.plan_removal(root, [ID_A])
    assert plan.exists
    assert plan.record_path == f"records/aa/{ID_A}.md"
    assert plan.artifact_path == f"artifacts/aa/{ID_A}.html"
    assert plan.artifact_size == 500
    assert plan.referrers == []


def test_find_artifact_ignores_part_temp_in_colocated_tree(tmp_path):
    # Regression: the co-located `artifacts/` scan matched ANY file whose stem was the
    # record id — including a `placement.put_at` `.part` temp left behind by an interrupted
    # write — while the store-location scan already excluded `.part`. A record with no
    # committed artifact but a stray `.part` temp must resolve as "no artifact", not the
    # temp file, in BOTH trees alike.
    root = _corpus(tmp_path)
    shard_dir = root / "artifacts" / paths.shard(ID_A)
    shard_dir.mkdir(parents=True)
    (shard_dir / f"{ID_A}.html.part").write_bytes(b"partial")

    apath, size, loc = maintenance._find_artifact(root, ID_A)
    assert apath is None
    assert size == 0
    assert loc is None


def test_find_artifact_still_finds_the_real_artifact_alongside_a_stray_part(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A, body=b"x" * 500)
    shard_dir = root / "artifacts" / paths.shard(ID_A)
    (shard_dir / f"{ID_A}.html.part").write_bytes(b"partial")

    apath, size, loc = maintenance._find_artifact(root, ID_A)
    assert apath is not None
    assert apath.name == f"{ID_A}.html"
    assert size == 500
    assert loc is None


def test_remove_dry_run_keeps_files(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A)
    result = maintenance.remove_records(root, [ID_A], execute=False)
    assert result.removed == [ID_A]
    assert result.dry_run is True
    assert paths.record_path(root, ID_A).exists()  # nothing deleted


def test_remove_executes_and_tidies(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A)
    result = maintenance.remove_records(root, [ID_A], execute=True)
    assert result.removed == [ID_A]
    assert not paths.record_path(root, ID_A).exists()
    assert not paths.artifact_path(root, ID_A, "html").exists()
    assert not (root / "records" / "aa").exists()
    assert not (root / "artifacts" / "aa").exists()


def test_remove_keep_artifact(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A)
    maintenance.remove_records(root, [ID_A], keep_artifact=True, execute=True)
    assert not paths.record_path(root, ID_A).exists()
    assert paths.artifact_path(root, ID_A, "html").exists()  # bytes retained


# ---------- rm: inbound reference check ---------- #


def _referrer(rid: str, target_id: str, *, via_url: str | None = None):
    """A record citing `target_id` via a reference block — tier 3 by default, tier 2 if
    `via_url` is given."""
    fields = {"source_url": via_url} if via_url else {"source_uri": f"corpus://{target_id}"}
    return {"namespace": "reference", "id": "ref", "subtype": "manual", "fields": fields}


def test_inbound_references_tier3(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A)
    _record(root, ID_B, contexts=[_referrer(ID_B, ID_A)])
    inbound = maintenance.inbound_references(root, {ID_A})
    assert [r.record_id for r in inbound[ID_A]] == [ID_B]
    assert inbound[ID_A][0].via == "reference/manual"


def test_inbound_references_tier2_resolved(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A, uri=URL_A)
    _record(root, ID_B, uri=URL_B, contexts=[_referrer(ID_B, ID_A, via_url=URL_A)])
    inbound = maintenance.inbound_references(root, {ID_A})
    assert [r.record_id for r in inbound[ID_A]] == [ID_B]


def test_remove_refuses_referenced_without_force(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A)
    _record(root, ID_B, contexts=[_referrer(ID_B, ID_A)])
    result = maintenance.remove_records(root, [ID_A], execute=True)
    assert result.blocked == [ID_A]
    assert result.removed == []
    assert paths.record_path(root, ID_A).exists()  # untouched


def test_remove_force_overrides_referrer(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A)
    _record(root, ID_B, contexts=[_referrer(ID_B, ID_A)])
    result = maintenance.remove_records(root, [ID_A], force=True, execute=True)
    assert result.removed == [ID_A]
    assert not paths.record_path(root, ID_A).exists()


# ---------- rm CLI ---------- #


def test_rm_cli_dry_run_by_default(tmp_path, capsys):
    root = _corpus(tmp_path)
    _record(root, ID_A)
    rc = dispatch(["rm", ID_A, "--corpus-root", str(root)])
    assert rc == 0
    assert "dry-run" in capsys.readouterr().out
    assert paths.record_path(root, ID_A).exists()


def test_rm_cli_yes_deletes(tmp_path, capsys):
    root = _corpus(tmp_path)
    _record(root, ID_A)
    rc = dispatch(["rm", ID_A, "--yes", "--corpus-root", str(root)])
    assert rc == 0
    assert not paths.record_path(root, ID_A).exists()


def test_rm_cli_blocked_returns_nonzero(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A)
    _record(root, ID_B, contexts=[_referrer(ID_B, ID_A)])
    rc = dispatch(["rm", ID_A, "--yes", "--corpus-root", str(root)])
    assert rc == 1
    assert paths.record_path(root, ID_A).exists()
    rc = dispatch(["rm", ID_A, "--force", "--corpus-root", str(root)])
    assert rc == 0
    assert not paths.record_path(root, ID_A).exists()


def test_rm_cli_unresolved_id_exits(tmp_path):
    root = _corpus(tmp_path)
    with pytest.raises(SystemExit):
        dispatch(["rm", "ff" * 32, "--corpus-root", str(root)])


# ---------- forget-origin ---------- #


def test_forget_origin_drops_alias(tmp_path):
    root = _corpus(tmp_path)
    post = _record(root, ID_A, uri=URL_A)
    records.append_origin_block(post, uri=URL_B, snapshot="2026-06-04T00:00:00Z")
    records.dump(post, paths.record_path(root, ID_A))

    result = maintenance.forget_origin(root, ID_A, URL_A)
    assert result.dropped and result.reason is None
    remaining = list(records.iter_origin_uris(records.load(paths.record_path(root, ID_A))))
    assert remaining == [URL_B]


def test_forget_origin_not_present(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A, uri=URL_A)
    result = maintenance.forget_origin(root, ID_A, "https://nope.test/")
    assert not result.dropped and result.reason == "not_present"
    assert list(records.iter_origin_uris(records.load(paths.record_path(root, ID_A)))) == [URL_A]


def test_forget_origin_last_origin_refuses(tmp_path):
    root = _corpus(tmp_path)
    _record(root, ID_A, uri=URL_A)
    result = maintenance.forget_origin(root, ID_A, URL_A)
    assert not result.dropped and result.reason == "last_origin"
    assert list(records.iter_origin_uris(records.load(paths.record_path(root, ID_A)))) == [URL_A]


def test_forget_origin_dry_run_writes_nothing(tmp_path):
    root = _corpus(tmp_path)
    post = _record(root, ID_A, uri=URL_A)
    records.append_origin_block(post, uri=URL_B, snapshot="2026-06-04T00:00:00Z")
    records.dump(post, paths.record_path(root, ID_A))

    result = maintenance.forget_origin(root, ID_A, URL_A, execute=False)
    assert result.dropped and result.dry_run
    after = list(records.iter_origin_uris(records.load(paths.record_path(root, ID_A))))
    assert after == [URL_A, URL_B]  # unchanged


def test_forget_origin_drops_emptied_block(tmp_path):
    """An alias that was the only uri of its block drops the whole block, keeping others."""
    root = _corpus(tmp_path)
    post = _record(root, ID_A, uri=URL_A)
    records.append_origin_block(post, uri=URL_B, snapshot="2026-06-04T00:00:00Z")
    records.dump(post, paths.record_path(root, ID_A))

    maintenance.forget_origin(root, ID_A, URL_B)
    reloaded = records.load(paths.record_path(root, ID_A))
    assert len(reloaded.metadata["_origins"]) == 1
    assert list(records.iter_origin_uris(reloaded)) == [URL_A]


def test_forget_origin_cli(tmp_path, capsys):
    root = _corpus(tmp_path)
    post = _record(root, ID_A, uri=URL_A)
    records.append_origin_block(post, uri=URL_B, snapshot="2026-06-04T00:00:00Z")
    records.dump(post, paths.record_path(root, ID_A))

    rc = dispatch(["forget-origin", ID_A, URL_A, "--corpus-root", str(root)])
    assert rc == 0
    assert "dropped" in capsys.readouterr().out

    rc = dispatch(["forget-origin", ID_A, "https://nope.test/", "--corpus-root", str(root)])
    assert rc == 1  # not present
    rc = dispatch(["forget-origin", ID_A, URL_B, "--corpus-root", str(root)])
    assert rc == 1  # last origin


# ---------- capture --force --replace ---------- #


def _fake_capture(new_id: str, url: str):
    """A `capture_and_ingest` stand-in that materializes a fresh HTML record for `url`."""

    def fake(u, *, corpus_root, opts=None):
        _record(corpus_root, new_id, uri=u)
        return paths.record_path(corpus_root, new_id)

    return fake


def test_capture_replace_retires_superseded(tmp_path, monkeypatch):
    root = _corpus(tmp_path)
    _record(root, ID_A, uri=URL_A)  # the prior full-chrome record
    monkeypatch.setattr("corpus.capture.capture_and_ingest", _fake_capture(ID_C, URL_A))

    rc = dispatch(["capture", URL_A, "--force", "--replace", "--corpus-root", str(root)])
    assert rc == 0
    assert paths.record_path(root, ID_C).exists()  # new record
    assert not paths.record_path(root, ID_A).exists()  # superseded one retired


def test_capture_replace_noop_when_bytes_identical(tmp_path, monkeypatch):
    root = _corpus(tmp_path)
    _record(root, ID_A, uri=URL_A)
    # Fold: re-capture resolves to the SAME id (identical bytes) — nothing to supersede.
    monkeypatch.setattr("corpus.capture.capture_and_ingest", _fake_capture(ID_A, URL_A))

    rc = dispatch(["capture", URL_A, "--force", "--replace", "--corpus-root", str(root)])
    assert rc == 0
    assert paths.record_path(root, ID_A).exists()  # not retired


def test_capture_replace_requires_force(tmp_path):
    root = _corpus(tmp_path)
    with pytest.raises(SystemExit):
        dispatch(["capture", URL_A, "--replace", "--corpus-root", str(root)])
