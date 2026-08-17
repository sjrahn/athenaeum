"""`corpus ingest`'s v20 hash-residency wiring (spec §2, §7.9, §8.1, §12.3.3, §12.9.1): the
resolved derived-hash recipe union — corpus-wide default set, layered with the matching mime
schema's `derived_hashes:` — computed while the staged bytes are in hand. `residency: record`
byte-stable values (`sha256`/`md5`) land in frontmatter `hash:`, never `transport:`; every
resolved value (record-resident or index-only) lands in the derived hash index, best-effort —
an index failure must never fail an otherwise-successful ingest.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import blake3

from corpus import hashindex, hashing, paths, records, schemas
from corpus._cli import ingest as ingest_cli


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)  # empty → packaged defaults only
    schemas.cache_clear()
    return root


def _ingest(root: Path, name: str, data: bytes) -> str:
    cap = root / "capture"
    cap.mkdir(exist_ok=True)
    staged = cap / name
    staged.write_bytes(data)
    assert ingest_cli._ingest_one(root, staged) == 0
    return blake3.blake3(data).hexdigest()


# Padded past the prefix ladder's 4 KiB rung but not its 64 KiB rung, so the ladder's
# partial-reach behavior (spec §7.9's registry table: "only rungs the file actually reaches
# are emitted") is exercised without a multi-megabyte fixture.
_HTML = (
    b"<!doctype html><html><head><title>hash wiring</title></head><body>"
    + b"<p>padding padding padding padding</p>" * 150
    + b"</body></html>"
)
assert 4 * 1024 < len(_HTML) < 64 * 1024


def test_html_ingest_writes_hash_and_index_rows(tmp_path):
    root = _corpus(tmp_path)
    rid = _ingest(root, "page.html", _HTML)

    record_file = paths.record_path(root, rid)
    text = record_file.read_text(encoding="utf-8")
    assert "transport:" not in text  # v20: never written

    post = records.load(record_file)
    assert records.media_type_for(post) == "text/html"

    entries = records.record_hashes(post)
    assert entries == {
        "sha256": hashlib.sha256(_HTML).hexdigest(),
        "md5": hashlib.md5(_HTML).hexdigest(),
    }
    # html-stampfree@1 is procedure-versioned — index-only, never on the record (spec §7.9).
    assert "html-stampfree@1" not in entries

    with hashindex.open_index(root) as conn:
        rows = hashindex.rows_for(conn, rid)
    by_algo = {r.algo: r for r in rows}

    # Record-resident values are mirrored into the index too (spec §2/§12.9.1).
    assert by_algo["sha256"].value == entries["sha256"]
    assert by_algo["md5"].value == entries["md5"]

    # The prefix ladder: only the rungs THIS file reaches (4 KiB, not 64 KiB / 1 MiB).
    assert "blake3-4k" in by_algo
    assert "blake3-64k" not in by_algo
    assert "blake3-1m" not in by_algo
    assert by_algo["blake3-4k"].value == blake3.blake3(_HTML[: 4 * 1024]).hexdigest()
    assert by_algo["blake3-4k"].param == str(4 * 1024)
    assert by_algo["blake3-4k"].recipe == "blake3-prefix-ladder"

    # html-stampfree@1 rides text/html's own `derived_hashes:` declaration, index-only.
    assert by_algo["html-stampfree@1"].value == hashing.html_stampfree_digest(_HTML)
    assert by_algo["html-stampfree@1"].recipe == "html-stampfree@1"


def test_non_html_ingest_gets_no_stampfree_row(tmp_path):
    root = _corpus(tmp_path)
    payload = b'{"padding": "' + b"x" * 200 + b'"}'
    rid = _ingest(root, "doc.json", payload)

    post = records.load(paths.record_path(root, rid))
    assert records.media_type_for(post) == "application/json"

    entries = records.record_hashes(post)
    assert entries == {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "md5": hashlib.md5(payload).hexdigest(),
    }

    with hashindex.open_index(root) as conn:
        rows = hashindex.rows_for(conn, rid)
    recipes = {r.recipe for r in rows}
    assert recipes <= {"sha256", "md5", "blake3-prefix-ladder"}
    assert "html-stampfree@1" not in recipes


def test_ingest_survives_a_broken_hash_index(tmp_path, monkeypatch):
    """The index is deployment state, never authoritative (spec §12.9.1) — a write failure
    must never fail an otherwise-successful ingest, and the record still gets its hash: entries
    (computed before the index write is even attempted)."""
    root = _corpus(tmp_path)

    def _boom(_corpus_root):
        raise RuntimeError("simulated index corruption")

    monkeypatch.setattr(hashindex, "connect", _boom)

    payload = b'{"resilient": "to a broken index"}'
    rid = _ingest(root, "resilient.json", payload)

    post = records.load(paths.record_path(root, rid))
    assert records.record_hashes(post) == {
        "sha256": hashlib.sha256(payload).hexdigest(),
        "md5": hashlib.md5(payload).hexdigest(),
    }
