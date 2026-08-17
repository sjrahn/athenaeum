"""`corpus hash flush` and `corpus hash-index backfill` (spec §12.9.1)."""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import hashindex, hashing, paths, records
from corpus._cli import dispatch

A = "a1" * 32
B = "b2" * 32


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _write_record(
    root: Path,
    rid: str,
    *,
    mime: str = "application/octet-stream",
    origin_uri: str = "https://example.com/page",
    hash_value: str | list[str] | None = None,
) -> Path:
    fm = records.stub_frontmatter(
        record_id=rid, hash_value=hash_value, touch_id="corpus.ingest@0.1.0"
    )
    post = frontmatter.Post(content="", **fm)
    records.set_artifact_block(post, mime=mime, fields={})
    records.append_origin_block(post, uri=origin_uri, snapshot="2026-08-16T00:00:00Z")
    record_path = paths.record_path(root, rid)
    records.dump(post, record_path)
    return record_path


def _write_artifact(root: Path, rid: str, ext: str, data: bytes) -> Path:
    art = paths.artifact_path(root, rid, ext)
    paths.ensure_parent(art)
    art.write_bytes(data)
    return art


# ---------- hash flush ---------- #


def test_flush_writes_identity_and_skips_similarity_and_unknown(tmp_path):
    hashing.register_recipe(
        hashing.Recipe(
            id="test-fake-simhash@1", residency="procedure-versioned", comparison="similarity"
        )
    )
    root = _corpus(tmp_path)
    record_path = _write_record(root, A)

    with hashindex.open_index(root) as conn:
        hashindex.upsert_rows(
            conn,
            [
                hashindex.HashRow(record_id=A, recipe="sha256", algo="sha256", value="1" * 64),
                hashindex.HashRow(
                    record_id=A,
                    recipe="test-fake-simhash@1",
                    algo="test-fake-simhash@1",
                    value="2" * 64,
                ),
                hashindex.HashRow(
                    record_id=A,
                    recipe="not-a-real-recipe",
                    algo="not-a-real-recipe",
                    value="3" * 64,
                ),
            ],
        )

    assert dispatch(["hash", "flush", A, "--corpus-root", str(root)]) == 0

    post = records.load(record_path)
    values = records.record_hashes(post)
    assert values == {"sha256": "1" * 64}


def test_flush_idempotent_second_run_is_zero_churn(tmp_path, capsys):
    root = _corpus(tmp_path)
    record_path = _write_record(root, A)
    with hashindex.open_index(root) as conn:
        hashindex.upsert_rows(
            conn, [hashindex.HashRow(record_id=A, recipe="sha256", algo="sha256", value="1" * 64)]
        )

    assert dispatch(["hash", "flush", A, "--corpus-root", str(root)]) == 0
    capsys.readouterr()
    before_text = record_path.read_text(encoding="utf-8")
    before_mtime = record_path.stat().st_mtime_ns

    assert dispatch(["hash", "flush", A, "--corpus-root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "0 value(s) written to 0 record(s)" in out

    after_text = record_path.read_text(encoding="utf-8")
    after_mtime = record_path.stat().st_mtime_ns
    assert after_text == before_text
    assert after_mtime == before_mtime


def test_flush_recipes_filter(tmp_path):
    root = _corpus(tmp_path)
    record_path = _write_record(root, A)
    with hashindex.open_index(root) as conn:
        hashindex.upsert_rows(
            conn,
            [
                hashindex.HashRow(record_id=A, recipe="sha256", algo="sha256", value="1" * 64),
                hashindex.HashRow(record_id=A, recipe="md5", algo="md5", value="2" * 32),
            ],
        )

    assert dispatch(
        ["hash", "flush", A, "--recipes", "sha256", "--corpus-root", str(root)]
    ) == 0

    post = records.load(record_path)
    values = records.record_hashes(post)
    assert values == {"sha256": "1" * 64}


def test_flush_all_flag(tmp_path):
    root = _corpus(tmp_path)
    _write_record(root, A)
    _write_record(root, B)
    with hashindex.open_index(root) as conn:
        hashindex.upsert_rows(
            conn,
            [
                hashindex.HashRow(record_id=A, recipe="sha256", algo="sha256", value="1" * 64),
                hashindex.HashRow(record_id=B, recipe="sha256", algo="sha256", value="4" * 64),
            ],
        )

    assert dispatch(["hash", "flush", "--all", "--corpus-root", str(root)]) == 0

    assert records.record_hashes(records.load(paths.record_path(root, A))) == {"sha256": "1" * 64}
    assert records.record_hashes(records.load(paths.record_path(root, B))) == {"sha256": "4" * 64}


# ---------- hash-index backfill ---------- #


def _html_bytes(size: int = 5000) -> bytes:
    filler = b"<!-- padding " + b"x" * size + b" -->"
    return b"<html><head></head><body>Hello world" + filler + b"</body></html>"


def test_backfill_fills_ladder_and_stampfree_for_html(tmp_path):
    root = _corpus(tmp_path)
    data = _html_bytes()
    rid = hashing.hash_bytes(data)["blake3"]
    _write_artifact(root, rid, "html", data)
    _write_record(root, rid, mime="text/html")

    rc = dispatch(["hash-index", "backfill", "--corpus-root", str(root)])
    assert rc == 0

    with hashindex.open_index(root) as conn:
        rows = hashindex.rows_for(conn, rid)
    recipes = {r.recipe for r in rows}
    assert recipes == {"sha256", "md5", "blake3-prefix-ladder", "html-stampfree@1"}
    tags = {r.algo for r in rows}
    assert "blake3-4k" in tags  # file is well over 4 KiB

    by_algo = {r.algo: r.value for r in rows}
    assert by_algo["html-stampfree@1"] == hashing.html_stampfree_digest(data)


def test_backfill_resume_only_recomputes_missing(tmp_path, monkeypatch):
    root = _corpus(tmp_path)
    data = _html_bytes()
    rid = hashing.hash_bytes(data)["blake3"]
    _write_artifact(root, rid, "html", data)
    _write_record(root, rid, mime="text/html")

    assert dispatch(["hash-index", "backfill", "--corpus-root", str(root)]) == 0
    with hashindex.open_index(root) as conn:
        before = {r.algo for r in hashindex.rows_for(conn, rid)}
    assert "md5" in before

    # Drop just the md5 row; everything else stays indexed.
    with hashindex.open_index(root) as conn:
        conn.execute(
            "DELETE FROM hashes WHERE record_id = ? AND algo = 'md5'", (rid,)
        )

    calls: list[list[str]] = []
    real_compute = hashing.compute_hashes

    def _counting_compute(path, recipes):
        recipes = list(recipes)
        calls.append([r.id for r in recipes])
        return real_compute(path, recipes)

    monkeypatch.setattr(hashing, "compute_hashes", _counting_compute)

    assert dispatch(["hash-index", "backfill", "--corpus-root", str(root)]) == 0

    assert len(calls) == 1
    assert calls[0] == ["md5"]  # only the missing recipe recomputed

    with hashindex.open_index(root) as conn:
        after = {r.algo for r in hashindex.rows_for(conn, rid)}
    assert after == before


def test_backfill_record_sync_indexes_record_resident_value_without_bytes(tmp_path):
    root = _corpus(tmp_path)
    fake_sha256 = "9" * 64
    # No artifact on disk at all for this record.
    _write_record(root, A, mime="application/octet-stream", hash_value=f"sha256:{fake_sha256}")

    rc = dispatch(["hash-index", "backfill", "--ids", A, "--corpus-root", str(root)])
    assert rc == 0  # non-fatal even though other recipes can't be resolved (see below)

    with hashindex.open_index(root) as conn:
        rows = {r.algo: r.value for r in hashindex.rows_for(conn, A)}
    assert rows["sha256"] == fake_sha256


def test_backfill_missing_artifact_skip_is_reported_not_fatal(tmp_path, capsys):
    root = _corpus(tmp_path)
    _write_record(root, A, mime="application/octet-stream")  # no artifact bytes anywhere

    rc = dispatch(["hash-index", "backfill", "--ids", A, "--corpus-root", str(root)])
    assert rc == 0

    out = capsys.readouterr().out
    assert "skip" in out
    assert "unresolvable" in out

    with hashindex.open_index(root) as conn:
        rows = hashindex.rows_for(conn, A)
    assert rows == []  # nothing computed — no bytes were ever found
