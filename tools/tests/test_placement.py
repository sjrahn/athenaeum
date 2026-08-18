"""Store-location placement — config parsing, `placement.py`, ingest wiring, byte
resolution, and refdata materialization (spec/corpus.md §12.1.1, v22 placement
amendment)."""

from __future__ import annotations

import errno
from pathlib import Path

import blake3
import pytest

from ath.manifest import Reference, Snapshot
from corpus import config as config_mod
from corpus import containment, paths, placement
from corpus._cli import ingest as ingest_cli
from refdata import materialize


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()  # empty -> packaged defaults only
    from corpus import schemas

    schemas.cache_clear()
    return root


def _write_toml(root: Path, text: str) -> None:
    (root / "corpus.toml").write_text(text, "utf-8")


# ---------- config parsing ---------- #


def test_store_location_with_ingest_list_parses(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "bulk"
kind = "store"
path = "{bulk}"
ingest = ["application/x-openzim", "application/json"]
""",
    )
    loc = config_mod.load_config(root).locations[0]
    assert loc.kind == "store"
    assert loc.ingest_types == ("application/x-openzim", "application/json")
    assert loc.ingest_default is False


def test_store_location_with_ingest_true_parses(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "bulk"
kind = "store"
path = "{bulk}"
ingest = true
""",
    )
    loc = config_mod.load_config(root).locations[0]
    assert loc.ingest_default is True
    assert loc.ingest_types == ()


def test_two_ingest_defaults_is_a_config_error(tmp_path):
    root = _corpus(tmp_path)
    a = tmp_path / "a"
    b = tmp_path / "b"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "a"
kind = "store"
path = "{a}"
ingest = true

[[corpus.location]]
name = "b"
kind = "store"
path = "{b}"
ingest = true
""",
    )
    with pytest.raises(ValueError, match="default ingest"):
        config_mod.load_config(root)


def test_ingest_key_on_attached_location_is_a_config_error(tmp_path):
    root = _corpus(tmp_path)
    d = tmp_path / "d"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "d"
kind = "attached"
path = "{d}"
ingest = true
""",
    )
    with pytest.raises(ValueError, match="only valid on"):
        config_mod.load_config(root)


def test_remote_key_is_not_implemented(tmp_path):
    root = _corpus(tmp_path)
    _write_toml(
        root,
        """
[[corpus.location]]
name = "offsite"
kind = "store"
path = "/mnt/slow/artifacts"
remote = "rclone:b2-corpus"
""",
    )
    with pytest.raises(ValueError, match="#204"):
        config_mod.load_config(root)


def test_ingest_wrong_shape_is_a_config_error(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "bulk"
kind = "store"
path = "{bulk}"
ingest = "application/json"
""",
    )
    with pytest.raises(ValueError, match="ingest"):
        config_mod.load_config(root)


# ---------- ingest_destination precedence ---------- #


def _loc(name, path, *, ingest_types=(), ingest_default=False):
    return config_mod.LocationConfig(
        name=name, kind="store", path=path, ingest_types=ingest_types, ingest_default=ingest_default
    )


def test_ingest_destination_format_list_beats_default(tmp_path):
    root = _corpus(tmp_path)
    default_path = tmp_path / "default"
    claim_path = tmp_path / "claim"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "default"
kind = "store"
path = "{default_path}"
ingest = true

[[corpus.location]]
name = "claim"
kind = "store"
path = "{claim_path}"
ingest = ["application/x-openzim"]
""",
    )
    dest = placement.ingest_destination(root, "application/x-openzim")
    assert dest is not None
    assert dest.name == "claim"

    # Anything NOT on the claim list still falls to the default.
    dest2 = placement.ingest_destination(root, "text/html")
    assert dest2 is not None
    assert dest2.name == "default"


def test_ingest_destination_none_when_nothing_claims_and_no_default(tmp_path):
    root = _corpus(tmp_path)
    claim = tmp_path / "claim"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "claim"
kind = "store"
path = "{claim}"
ingest = ["application/x-openzim"]
""",
    )
    assert placement.ingest_destination(root, "text/html") is None


def test_ingest_destination_none_with_no_store_locations(tmp_path):
    root = _corpus(tmp_path)
    assert placement.ingest_destination(root, "text/html") is None


# ---------- put_at ---------- #


def test_put_at_same_device_rename_leaves_no_part_file(tmp_path):
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    loc = _loc("bulk", bulk)
    src = tmp_path / "staged.bin"
    src.write_bytes(b"hello store")

    dst = placement.put_at(loc, "a" * 64, "bin", src)

    assert dst == placement.location_artifact_path(loc, "a" * 64, "bin")
    assert dst.read_bytes() == b"hello store"
    assert not src.exists()  # same-device rename moved it away
    assert not dst.with_name(dst.name + ".part").exists()


def test_put_at_cross_device_fallback_copies_and_leaves_src(tmp_path, monkeypatch):
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    loc = _loc("bulk", bulk)
    src = tmp_path / "staged.bin"
    src.write_bytes(b"cross device bytes")

    def _raise_exdev(_a, _b):
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(placement.os, "rename", _raise_exdev)

    dst = placement.put_at(loc, "b" * 64, "bin", src)

    assert dst.read_bytes() == b"cross device bytes"
    assert src.exists()  # copy, not move — caller's staging unlink cleans it up
    assert not dst.with_name(dst.name + ".part").exists()


def test_put_at_other_oserror_propagates(tmp_path, monkeypatch):
    bulk = tmp_path / "bulk"
    bulk.mkdir()
    loc = _loc("bulk", bulk)
    src = tmp_path / "does-not-exist.bin"  # triggers a real (non-EXDEV) OSError

    with pytest.raises(OSError):
        placement.put_at(loc, "c" * 64, "bin", src)


# ---------- containment: ensure_local_bytes through a store location ---------- #


def test_ensure_local_bytes_resolves_store_location_file(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "bulk"
kind = "store"
path = "{bulk}"
""",
    )
    data = b"bytes living only in a store location"
    digest = blake3.blake3(data).hexdigest()
    dest = bulk / paths.shard(digest) / f"{digest}.bin"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(data)

    resolved = containment.ensure_local_bytes(root, digest, "bin")
    assert resolved == dest
    assert resolved.read_bytes() == data


# ---------- ingest end-to-end: a store location claims a format ---------- #


_HTML = b"<!doctype html><html><head><title>placement</title></head><body>hi</body></html>"


def test_ingest_places_claimed_format_in_store_location(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "bulk"
kind = "store"
path = "{bulk}"
ingest = ["text/html"]
""",
    )
    capture = root / "capture"
    capture.mkdir()
    staged = capture / "page.html"
    staged.write_bytes(_HTML)

    assert ingest_cli._ingest_one(root, staged) == 0

    digest = blake3.blake3(_HTML).hexdigest()
    expected = bulk / paths.shard(digest) / f"{digest}.html"
    assert expected.is_file()
    assert expected.read_bytes() == _HTML

    # Nothing landed in the co-located tree, and staging is gone.
    assert not paths.artifact_path(root, digest, "html").exists()
    assert not staged.exists()

    # The record resolves its bytes through the store location.
    resolved = containment.ensure_local_bytes(root, digest, "html")
    assert resolved == expected


def test_ingest_unclaimed_format_still_lands_co_located(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "bulk"
kind = "store"
path = "{bulk}"
ingest = ["application/x-openzim"]
""",
    )
    capture = root / "capture"
    capture.mkdir()
    staged = capture / "page.html"
    staged.write_bytes(_HTML)

    assert ingest_cli._ingest_one(root, staged) == 0

    digest = blake3.blake3(_HTML).hexdigest()
    assert paths.artifact_path(root, digest, "html").is_file()


# ---------- refdata materialization through a store location ---------- #


def test_refdata_materializes_through_store_location(tmp_path):
    root = _corpus(tmp_path)
    bulk = tmp_path / "bulk"
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "bulk"
kind = "store"
path = "{bulk}"
""",
    )
    data = b"mirror snapshot bytes"
    digest = blake3.blake3(data).hexdigest()
    dest = bulk / paths.shard(digest) / f"{digest}.zim"
    dest.parent.mkdir(parents=True)
    dest.write_bytes(data)

    ref = Reference(
        dataset="testplacement", description="test mirror", adapter="zim",
        latest="t", snapshots={"t": Snapshot(artifact=digest)},
    )
    resolved = materialize(ref, "t", corpora_roots=(root,))
    assert resolved == dest


def test_mirror_format_extensions_are_canonical():
    # Regression: without canonical entries these derived "bin" via the fallback,
    # while ingest's source-suffix fallback wrote .pbf/.zim to disk — so every
    # corpus-root-free extension_for caller (move, health) missed the artifact.
    from corpus import mime

    assert mime.extension_for("application/x-openzim") == "zim"
    assert mime.extension_for("application/x-osm+pbf") == "pbf"
