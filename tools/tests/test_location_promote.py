"""`corpus location promote` — minting a record for an attested location file, bytes
staying in place (spec §12.1.1, §12.9.2, v21 custody amendment).

Identity is re-verified in full at mint (blake3 over the whole file), the origin block
carries `file://<absolute path>` provenance (plus any `--source-url` alias in the same
block), and the artifact-store `put` is skipped entirely — the record is otherwise
byte-indistinguishable from a normal `corpus ingest` record.

Test files use `.json` payloads: `application/json` ships a default mime schema
(`text/plain` does not — no subtype schema for it exists), and `corpus location promote`
requires a matching schema, the same as `corpus ingest` (spec: byte-indistinguishable
from an ingest-minted record).
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

from corpus import config as config_mod
from corpus import containment, hashindex, hashing, locationindex, paths, records, schemas
from corpus._cli import location as location_cli
from corpus.store import LocalArtifactStore


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _attach(root: Path, tree: Path, *, name: str = "loc") -> config_mod.LocationConfig:
    (root / "corpus.toml").write_text(
        f"""
[[corpus.location]]
name = "{name}"
kind = "attached"
path = "{tree}"
""",
        "utf-8",
    )
    loc = config_mod.load_config(root).locations[0]
    locationindex.attest_location(root, loc)
    return loc


def _promote(
    root: Path,
    name: str,
    relpath: str | None = None,
    *,
    all_matching: str | None = None,
    source_urls: list[str] | None = None,
) -> int:
    return location_cli.run(
        argparse.Namespace(
            action="promote",
            name=name,
            relpath=relpath,
            all_matching=all_matching,
            source_urls=source_urls or [],
            corpus_root=str(root),
        )
    )


def _origins(root: Path, rid: str) -> list[dict]:
    return list(records.iter_origin_blocks(records.load(paths.record_path(root, rid))))


# ---------- happy path ---------- #


def test_promote_mints_record_with_file_uri_origin(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    data = b'{"hello": "from an attached location"}\n'
    f.write_bytes(data)
    _attach(root, tree)

    assert _promote(root, "loc", "a.json") == 0
    out = capsys.readouterr().out
    assert "promoted:" in out

    rid = hashing.hash_file(f, also=())["blake3"]
    record_file = paths.record_path(root, rid)
    assert record_file.is_file()

    post = records.load(record_file)
    assert post.metadata["id"] == rid
    assert records.media_type_for(post) == "application/json"
    assert records.derived_state(post) == "proxy"

    origin = _origins(root, rid)[0]["fields"]
    assert origin["uri"] == f.as_uri()

    # hash: carries the record-resident default set (sha256/md5).
    hashes = records.record_hashes(post)
    assert "sha256" in hashes
    assert "md5" in hashes

    # Bytes were NOT copied into artifacts/.
    assert not LocalArtifactStore(root).is_local(rid, "json")
    artifacts_dir = root / "artifacts"
    if artifacts_dir.is_dir():
        assert list(artifacts_dir.rglob("*")) == []


def test_promote_source_url_adds_alias_in_same_block(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"case": "source-url"}\n')
    _attach(root, tree)

    url = "https://example.org/dataset/a.json"
    assert _promote(root, "loc", "a.json", source_urls=[url]) == 0

    rid = hashing.hash_file(f, also=())["blake3"]
    origin = _origins(root, rid)[0]["fields"]
    assert origin["uri"] == [f.as_uri(), url]


def test_ensure_local_bytes_resolves_promoted_record(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    data = b'{"resolve": "me"}\n'
    f.write_bytes(data)
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0

    rid = hashing.hash_file(f, also=())["blake3"]
    resolved = containment.ensure_local_bytes(root, rid, "json")
    assert resolved == f
    assert resolved.read_bytes() == data


def test_promote_writes_hashes_db_rows(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"index": "me"}\n')
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0

    rid = hashing.hash_file(f, also=())["blake3"]
    with hashindex.open_index(root) as conn:
        rows = hashindex.rows_for(conn, rid)
    algos = {row.algo for row in rows}
    assert "sha256" in algos
    assert "md5" in algos
    # The blake3 prefix ladder only emits a rung once the file reaches it (shortest rung
    # 4 KiB) — this fixture is well under that, so no ladder rows here; index-write
    # plumbing is what this test is really checking.


def test_promoted_record_lints_clean(tmp_path):
    from corpus import lint, segments

    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"lint": "me"}\n')
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0

    rid = hashing.hash_file(f, also=())["blake3"]
    post = records.load(paths.record_path(root, rid))
    blocks = segments.iter_blocks(post.content or "")
    findings = lint.lint(post, blocks, root)
    # No findings at ERROR severity — a freshly minted proxy stub is allowed to be
    # unformed (that's not a lint error), but nothing about its shape should be flagged.
    errors = [fnd for fnd in findings if getattr(fnd, "severity", "") == "error"]
    assert errors == []


# ---------- idempotence ---------- #


def test_re_promote_is_a_no_op(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"idempotent": true}\n')
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0

    rid = hashing.hash_file(f, also=())["blake3"]
    before = records.load(paths.record_path(root, rid))
    origins_before = _origins(root, rid)

    assert _promote(root, "loc", "a.json") == 0
    after = records.load(paths.record_path(root, rid))
    origins_after = _origins(root, rid)

    assert origins_before == origins_after
    assert before.metadata["id"] == after.metadata["id"]


def test_re_promote_with_new_source_url_adds_alias(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"alias": "later"}\n')
    _attach(root, tree)
    assert _promote(root, "loc", "a.json") == 0

    rid = hashing.hash_file(f, also=())["blake3"]
    url = "https://example.org/later.json"
    assert _promote(root, "loc", "a.json", source_urls=[url]) == 0

    origin = _origins(root, rid)[0]["fields"]
    uri = origin["uri"]
    uris = uri if isinstance(uri, list) else [uri]
    assert f.as_uri() in uris
    assert url in uris


# ---------- refusals ---------- #


def test_promote_unattested_relpath_is_actionable_error(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.json").write_bytes(b'{"attested": true}\n')
    _attach(root, tree)
    (tree / "b.json").write_bytes(b'{"attested": false}\n')

    assert _promote(root, "loc", "b.json") == 1
    err = capsys.readouterr().err
    assert "corpus location attest" in err
    assert "loc" in err


def test_promote_tampered_file_refuses_and_names_reattest(tmp_path, capsys):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.json"
    f.write_bytes(b'{"v": "original"}\n')
    _attach(root, tree)

    f.write_bytes(b'{"v": "tampered after attest"}\n')

    assert _promote(root, "loc", "a.json") == 1
    err = capsys.readouterr().err
    assert "corpus location attest" in err
    # No record minted for the stale/tampered attempt.
    assert list(root.glob("records/*/*.md")) == []


# ---------- batch ---------- #


def test_all_matching_promotes_the_matching_set(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.json").write_bytes(b'{"n": "a"}\n')
    (tree / "b.json").write_bytes(b'{"n": "b"}\n')
    (tree / "c.dat").write_bytes(b"not-json\n")
    _attach(root, tree)

    assert _promote(root, "loc", all_matching="*.json") == 0

    rid_a = hashing.hash_file(tree / "a.json", also=())["blake3"]
    rid_b = hashing.hash_file(tree / "b.json", also=())["blake3"]
    rid_c = hashing.hash_file(tree / "c.dat", also=())["blake3"]

    assert paths.record_path(root, rid_a).is_file()
    assert paths.record_path(root, rid_b).is_file()
    assert not paths.record_path(root, rid_c).is_file()


def test_all_matching_with_source_url_is_rejected(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.json").write_bytes(b"{}\n")
    _attach(root, tree)

    with pytest.raises(SystemExit):
        _promote(root, "loc", all_matching="*.json", source_urls=["https://example.org/x"])


def test_relpath_and_all_matching_together_is_rejected(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.json").write_bytes(b"{}\n")
    _attach(root, tree)

    with pytest.raises(SystemExit):
        _promote(root, "loc", "a.json", all_matching="*.json")


def test_neither_relpath_nor_all_matching_is_rejected(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    _attach(root, tree)

    with pytest.raises(SystemExit):
        _promote(root, "loc")
