"""The derived hash index (spec §12.9.1)."""

from __future__ import annotations

import frontmatter

from corpus import hashindex


def _row(record_id: str, tag: str, hexval: str, *, recipe: str | None = None, param: str = ""):
    return hashindex.HashRow(
        record_id=record_id, recipe=recipe or tag, algo=tag, value=hexval, param=param
    )


def test_upsert_and_rows_for(tmp_path):
    with hashindex.open_index(tmp_path) as conn:
        n = hashindex.upsert_rows(conn, [_row("a" * 64, "sha256", "1" * 64)])
        assert n == 1
        rows = hashindex.rows_for(conn, "a" * 64)
        assert len(rows) == 1
        assert rows[0].algo == "sha256"
        assert rows[0].value == "1" * 64
        assert rows[0].encoded() == "sha256:" + "1" * 64


def test_upsert_is_idempotent():
    root = None
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        with hashindex.open_index(root) as conn:
            row = _row("a" * 64, "sha256", "1" * 64)
            hashindex.upsert_rows(conn, [row])
            hashindex.upsert_rows(conn, [row])
            hashindex.upsert_rows(conn, [row])
            rows = hashindex.rows_for(conn, "a" * 64)
            assert len(rows) == 1  # same key, still one row


def test_upsert_overwrites_value_on_same_key(tmp_path):
    with hashindex.open_index(tmp_path) as conn:
        hashindex.upsert_rows(conn, [_row("a" * 64, "sha256", "1" * 64)])
        hashindex.upsert_rows(conn, [_row("a" * 64, "sha256", "2" * 64)])
        rows = hashindex.rows_for(conn, "a" * 64)
        assert len(rows) == 1
        assert rows[0].value == "2" * 64


def test_upsert_distinguishes_by_param(tmp_path):
    with hashindex.open_index(tmp_path) as conn:
        hashindex.upsert_rows(
            conn,
            [
                _row("a" * 64, "blake3-4k", "1" * 64, recipe="blake3-prefix-ladder", param="4096"),
                _row(
                    "a" * 64, "blake3-64k", "2" * 64, recipe="blake3-prefix-ladder", param="65536"
                ),
            ],
        )
        rows = hashindex.rows_for(conn, "a" * 64)
        assert len(rows) == 2
        params = {r.param for r in rows}
        assert params == {"4096", "65536"}


def test_values_by_algo_join_query(tmp_path):
    with hashindex.open_index(tmp_path) as conn:
        hashindex.upsert_rows(
            conn,
            [
                _row("a" * 64, "html-stampfree@1", "same" * 16),
                _row("b" * 64, "html-stampfree@1", "same" * 16),
                _row("c" * 64, "html-stampfree@1", "diff" * 16),
            ],
        )
        grouped = hashindex.values_by_algo(conn, "html-stampfree@1")
        assert grouped["same" * 16] == ["a" * 64, "b" * 64]
        assert grouped["diff" * 16] == ["c" * 64]


def test_missing_recipes_query(tmp_path):
    with hashindex.open_index(tmp_path) as conn:
        hashindex.upsert_rows(conn, [_row("a" * 64, "sha256", "1" * 64)])
        result = hashindex.missing(conn, ["a" * 64, "b" * 64], ["sha256", "md5"])
        assert result["a" * 64] == ["md5"]
        assert result["b" * 64] == ["sha256", "md5"]


def test_missing_recipe_present_via_any_rung(tmp_path):
    """A multi-value recipe with only SOME rungs indexed is not "missing" — presence is
    checked by recipe, not by exhaustive rung coverage (a short file legitimately never
    reaches every rung)."""
    with hashindex.open_index(tmp_path) as conn:
        hashindex.upsert_rows(
            conn,
            [_row("a" * 64, "blake3-4k", "1" * 64, recipe="blake3-prefix-ladder", param="4096")],
        )
        result = hashindex.missing(conn, ["a" * 64], ["blake3-prefix-ladder"])
        assert result == {}


def test_missing_empty_inputs(tmp_path):
    with hashindex.open_index(tmp_path) as conn:
        assert hashindex.missing(conn, [], ["sha256"]) == {}
        assert hashindex.missing(conn, ["a" * 64], []) == {}


def test_delete_record(tmp_path):
    with hashindex.open_index(tmp_path) as conn:
        hashindex.upsert_rows(
            conn,
            [_row("a" * 64, "sha256", "1" * 64), _row("a" * 64, "md5", "2" * 32)],
        )
        n = hashindex.delete_record(conn, "a" * 64)
        assert n == 2
        assert hashindex.rows_for(conn, "a" * 64) == []


def _post_with_hash(record_id: str, hash_value):
    post = frontmatter.Post("")
    post.metadata.update({"id": record_id, "hash": hash_value})
    return post


def test_sync_from_records(tmp_path):
    refs = [
        ("a" * 64, _post_with_hash("a" * 64, "sha256:" + "1" * 64)),
        (
            "b" * 64,
            _post_with_hash(
                "b" * 64, ["sha256:" + "2" * 64, "html-stampfree@1:" + "3" * 64]
            ),
        ),
        ("c" * 64, _post_with_hash("c" * 64, None)),  # no hash field — nothing to sync
    ]
    n = hashindex.sync_from_records(tmp_path, refs)
    assert n == 3  # a: 1 row, b: 2 rows, c: 0 rows

    with hashindex.open_index(tmp_path) as conn:
        a_rows = hashindex.rows_for(conn, "a" * 64)
        assert len(a_rows) == 1
        assert a_rows[0].algo == "sha256"
        assert a_rows[0].value == "1" * 64

        b_rows = {r.algo: r.value for r in hashindex.rows_for(conn, "b" * 64)}
        assert b_rows == {"sha256": "2" * 64, "html-stampfree@1": "3" * 64}

        assert hashindex.rows_for(conn, "c" * 64) == []


def test_sync_from_records_recovers_recipe_from_tag():
    """A record-resident value carries no recipe id in the frontmatter — the sync
    recovers it from the tag (a single-value recipe's id equals its tag, §7.9)."""
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        refs = [("a" * 64, _post_with_hash("a" * 64, "html-stampfree@1:" + "9" * 64))]
        hashindex.sync_from_records(root, refs)
        with hashindex.open_index(root) as conn:
            rows = hashindex.rows_for(conn, "a" * 64)
            assert len(rows) == 1
            assert rows[0].recipe == "html-stampfree@1"
            assert rows[0].algo == "html-stampfree@1"


def test_rebuild_from_wipe_resyncs_record_resident_rows(tmp_path):
    """Deleting `hashes.db` and re-running `sync_from_records` restores every
    record-resident row from `records/` alone — no bytes needed (spec §12.9.1)."""
    refs = [("a" * 64, _post_with_hash("a" * 64, "sha256:" + "1" * 64))]
    hashindex.sync_from_records(tmp_path, refs)

    db = hashindex.db_path(tmp_path)
    assert db.is_file()
    db.unlink()
    # WAL sidecar files, if any, are harmless to leave — a fresh connect recreates the schema.

    with hashindex.open_index(tmp_path) as conn:
        assert hashindex.rows_for(conn, "a" * 64) == []  # wiped

    hashindex.sync_from_records(tmp_path, refs)
    with hashindex.open_index(tmp_path) as conn:
        rows = hashindex.rows_for(conn, "a" * 64)
        assert len(rows) == 1
        assert rows[0].value == "1" * 64


def test_db_path_creates_cache_dir(tmp_path):
    path = hashindex.db_path(tmp_path)
    assert path == tmp_path / "cache" / "hashes.db"
    assert (tmp_path / "cache").is_dir()
