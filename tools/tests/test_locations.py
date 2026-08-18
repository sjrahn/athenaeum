"""Attached locations — config parsing, the location index, and containment
integration (spec §12.1.1, §12.9.2, v21 custody amendment)."""

from __future__ import annotations

from pathlib import Path

import pytest

from corpus import config as config_mod
from corpus import containment, hashing, locationindex


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _write_toml(root: Path, text: str) -> None:
    (root / "corpus.toml").write_text(text, "utf-8")


# ---------- config parsing ---------- #


def test_no_locations_configured_is_empty_and_unchanged(tmp_path):
    root = _corpus(tmp_path)
    cfg = config_mod.load_config(root)
    assert cfg.locations == ()


def test_valid_attached_location_parses(tmp_path):
    root = _corpus(tmp_path)
    data_dir = tmp_path / "datasets"
    data_dir.mkdir()
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "datasets"
kind = "attached"
path = "{data_dir}"
""",
    )
    cfg = config_mod.load_config(root)
    assert len(cfg.locations) == 1
    loc = cfg.locations[0]
    assert loc.name == "datasets"
    assert loc.kind == "attached"
    assert loc.path == data_dir


def test_store_kind_with_local_path_parses(tmp_path):
    # (v22) store kind is implemented now — config parsing detail lives in
    # test_placement.py; this just confirms the old not-implemented rejection is gone.
    root = _corpus(tmp_path)
    _write_toml(
        root,
        """
[[corpus.location]]
name = "bulk"
kind = "store"
path = "/mnt/slow/artifacts"
""",
    )
    cfg = config_mod.load_config(root)
    assert cfg.locations[0].kind == "store"


def test_remote_key_not_implemented_error(tmp_path):
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
    with pytest.raises(ValueError, match="not implemented"):
        config_mod.load_config(root)


def test_unknown_kind_is_config_error(tmp_path):
    root = _corpus(tmp_path)
    _write_toml(
        root,
        """
[[corpus.location]]
name = "weird"
kind = "bogus"
path = "/tmp/whatever"
""",
    )
    with pytest.raises(ValueError, match="unknown kind"):
        config_mod.load_config(root)


def test_duplicate_names_error(tmp_path):
    root = _corpus(tmp_path)
    d1 = tmp_path / "d1"
    d2 = tmp_path / "d2"
    d1.mkdir()
    d2.mkdir()
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "dup"
kind = "attached"
path = "{d1}"

[[corpus.location]]
name = "dup"
kind = "attached"
path = "{d2}"
""",
    )
    with pytest.raises(ValueError, match="duplicate name"):
        config_mod.load_config(root)


def test_missing_path_error(tmp_path):
    root = _corpus(tmp_path)
    _write_toml(
        root,
        """
[[corpus.location]]
name = "nopath"
kind = "attached"
""",
    )
    with pytest.raises(ValueError, match="path"):
        config_mod.load_config(root)


def test_relative_path_error(tmp_path):
    root = _corpus(tmp_path)
    _write_toml(
        root,
        """
[[corpus.location]]
name = "rel"
kind = "attached"
path = "relative/dir"
""",
    )
    with pytest.raises(ValueError, match="absolute"):
        config_mod.load_config(root)


# ---------- manifest key (spec §12.1.1, v24) ---------- #


def test_manifest_key_accepted_on_attached(tmp_path):
    root = _corpus(tmp_path)
    data_dir = tmp_path / "datasets"
    data_dir.mkdir()
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "datasets"
kind = "attached"
path = "{data_dir}"
manifest = true
""",
    )
    cfg = config_mod.load_config(root)
    assert cfg.locations[0].manifest is True


def test_manifest_key_defaults_false(tmp_path):
    root = _corpus(tmp_path)
    data_dir = tmp_path / "datasets"
    data_dir.mkdir()
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "datasets"
kind = "attached"
path = "{data_dir}"
""",
    )
    cfg = config_mod.load_config(root)
    assert cfg.locations[0].manifest is False


def test_manifest_key_refused_on_store(tmp_path):
    root = _corpus(tmp_path)
    _write_toml(
        root,
        """
[[corpus.location]]
name = "bulk"
kind = "store"
path = "/mnt/slow/artifacts"
manifest = true
""",
    )
    with pytest.raises(ValueError, match="attached"):
        config_mod.load_config(root)


def test_manifest_key_non_bool_error(tmp_path):
    root = _corpus(tmp_path)
    data_dir = tmp_path / "datasets"
    data_dir.mkdir()
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "datasets"
kind = "attached"
path = "{data_dir}"
manifest = "yes"
""",
    )
    with pytest.raises(ValueError, match="bool"):
        config_mod.load_config(root)


# ---------- attest pass ---------- #


def _loc(name: str, path: Path) -> config_mod.LocationConfig:
    return config_mod.LocationConfig(name=name, kind="attached", path=path)


def test_attest_counts_and_incremental_rerun(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.txt").write_bytes(b"hello world")
    (tree / "sub").mkdir()
    (tree / "sub" / "b.txt").write_bytes(b"goodbye world")
    loc = _loc("t", tree)

    counts = locationindex.attest_location(root, loc)
    assert counts == {"files": 2, "hashed": 2, "unchanged": 0, "removed": 0}

    # Re-run with no changes: nothing re-hashed.
    counts2 = locationindex.attest_location(root, loc)
    assert counts2 == {"files": 2, "hashed": 0, "unchanged": 2, "removed": 0}


def test_attest_rehashes_touched_file(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.txt"
    f.write_bytes(b"hello world")
    loc = _loc("t", tree)
    locationindex.attest_location(root, loc)

    # Modify content (a real filesystem write moves mtime forward).
    f.write_bytes(b"hello world, changed")

    counts = locationindex.attest_location(root, loc)
    assert counts == {"files": 1, "hashed": 1, "unchanged": 0, "removed": 0}


def test_attest_removes_deleted_file_row(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.txt"
    f.write_bytes(b"hello world")
    loc = _loc("t", tree)
    locationindex.attest_location(root, loc)

    f.unlink()
    counts = locationindex.attest_location(root, loc)
    assert counts == {"files": 0, "hashed": 0, "unchanged": 0, "removed": 1}

    with locationindex.open_index(root) as conn:
        rows = conn.execute("SELECT * FROM locations WHERE location = 't'").fetchall()
    assert rows == []


def test_attest_indexes_wanted_dotfiles(tmp_path):
    """The walking attest no longer blanket-skips hidden files (owner ruling): only the
    curated junk deny-list is excluded. A plain dotfile or a `.git` directory's contents
    are ordinary attached content and get indexed like anything else."""
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.txt").write_bytes(b"visible")
    (tree / ".hidden").write_bytes(b"a wanted dotfile, now indexed")
    (tree / ".git").mkdir()
    (tree / ".git" / "config").write_bytes(b"also indexed now")
    loc = _loc("t", tree)

    counts = locationindex.attest_location(root, loc)
    assert counts["files"] == 3


def test_attest_skips_junk_deny_list_and_prunes_matched_dirs(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    (tree / "a.txt").write_bytes(b"keep")
    (tree / "._junk").write_bytes(b"AppleDouble sidecar")
    (tree / ".DS_Store").write_bytes(b"finder junk")
    (tree / "@eaDir").mkdir()
    (tree / "@eaDir" / "thumb.jpg").write_bytes(b"synology junk under a pruned subtree")
    (tree / ".athenaeum").mkdir()
    (tree / ".athenaeum" / "manifest.sqlite").write_bytes(b"scanner infra, always pruned")
    loc = _loc("t", tree)

    counts = locationindex.attest_location(root, loc)
    assert counts["files"] == 1

    with locationindex.open_index(root) as conn:
        rows = {r[0] for r in conn.execute(
            "SELECT relpath FROM locations WHERE location = 't'"
        ).fetchall()}
    assert rows == {"a.txt"}


def test_attest_progress_callback_invoked(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    for i in range(1200):
        (tree / f"f{i}.txt").write_bytes(str(i).encode())
    loc = _loc("t", tree)

    calls: list[int] = []
    locationindex.attest_location(root, loc, progress=calls.append)
    assert calls == [500, 1000]


def test_attest_missing_dir_errors(tmp_path):
    root = _corpus(tmp_path)
    loc = _loc("t", tmp_path / "does-not-exist")
    with pytest.raises(ValueError, match="not a directory"):
        locationindex.attest_location(root, loc)


# ---------- route_for / stale_rows ---------- #


def test_route_for_known_and_unknown_hash(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.txt"
    data = b"hello world"
    f.write_bytes(data)
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "t"
kind = "attached"
path = "{tree}"
""",
    )
    loc = config_mod.load_config(root).locations[0]
    locationindex.attest_location(root, loc)

    digest = hashing.hash_file(f, also=())["blake3"]
    resolved = locationindex.route_for(root, digest)
    assert resolved == f

    assert locationindex.route_for(root, "0" * 64) is None


def test_route_for_stale_after_modification_then_valid_after_reattest(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.txt"
    f.write_bytes(b"hello world")
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "t"
kind = "attached"
path = "{tree}"
""",
    )
    loc = config_mod.load_config(root).locations[0]
    locationindex.attest_location(root, loc)
    digest = hashing.hash_file(f, also=())["blake3"]
    assert locationindex.route_for(root, digest) == f

    # Tamper: change content/mtime without re-attesting -> stale pin -> None.
    f.write_bytes(b"tampered content")
    assert locationindex.route_for(root, digest) is None

    # Re-attest: the row now points at the new hash, and the new hash resolves.
    locationindex.attest_location(root, loc)
    new_digest = hashing.hash_file(f, also=())["blake3"]
    assert locationindex.route_for(root, new_digest) == f


def test_stale_rows_lists_tampered_file(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "a.txt"
    f.write_bytes(b"hello world")
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "t"
kind = "attached"
path = "{tree}"
""",
    )
    loc = config_mod.load_config(root).locations[0]
    locationindex.attest_location(root, loc)
    assert locationindex.stale_rows(root) == []

    f.write_bytes(b"tampered")
    stale = locationindex.stale_rows(root)
    assert len(stale) == 1
    assert stale[0][0] == "t"
    assert stale[0][1] == "a.txt"


# ---------- route_for cost ordering (spec §12.1.1, v25 "Route preference") ---------- #


def test_route_for_prefers_cheaper_location(tmp_path):
    root = _corpus(tmp_path)
    cheap_tree = tmp_path / "cheap"
    pricey_tree = tmp_path / "pricey"
    cheap_tree.mkdir()
    pricey_tree.mkdir()
    data = b"same bytes in two attached locations"
    (cheap_tree / "a.bin").write_bytes(data)
    (pricey_tree / "a.bin").write_bytes(data)
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "pricey"
kind = "attached"
path = "{pricey_tree}"
cost = 99

[[corpus.location]]
name = "cheap"
kind = "attached"
path = "{cheap_tree}"
cost = 1
""",
    )
    for loc in config_mod.load_config(root).locations:
        locationindex.attest_location(root, loc)

    digest = hashing.hash_file(cheap_tree / "a.bin", also=())["blake3"]
    assert locationindex.route_for(root, digest) == cheap_tree / "a.bin"


def test_route_for_falls_through_to_costlier_when_cheaper_stale(tmp_path):
    root = _corpus(tmp_path)
    cheap_tree = tmp_path / "cheap"
    pricey_tree = tmp_path / "pricey"
    cheap_tree.mkdir()
    pricey_tree.mkdir()
    data = b"same bytes, one goes stale"
    (cheap_tree / "a.bin").write_bytes(data)
    (pricey_tree / "a.bin").write_bytes(data)
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "cheap"
kind = "attached"
path = "{cheap_tree}"
cost = 1

[[corpus.location]]
name = "pricey"
kind = "attached"
path = "{pricey_tree}"
cost = 99
""",
    )
    for loc in config_mod.load_config(root).locations:
        locationindex.attest_location(root, loc)

    digest = hashing.hash_file(cheap_tree / "a.bin", also=())["blake3"]
    assert locationindex.route_for(root, digest) == cheap_tree / "a.bin"

    # Tamper the cheap copy without re-attesting: its row goes stale, so the costlier
    # CURRENT row must serve instead (falling through exactly as routes fall through
    # today, spec §12.1.1 v25).
    (cheap_tree / "a.bin").write_bytes(b"tampered")
    assert locationindex.route_for(root, digest) == pricey_tree / "a.bin"


def test_route_for_declaration_order_breaks_cost_tie(tmp_path):
    root = _corpus(tmp_path)
    first_tree = tmp_path / "first"
    second_tree = tmp_path / "second"
    first_tree.mkdir()
    second_tree.mkdir()
    data = b"tied cost, declaration order decides"
    (first_tree / "a.bin").write_bytes(data)
    (second_tree / "a.bin").write_bytes(data)
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "first"
kind = "attached"
path = "{first_tree}"

[[corpus.location]]
name = "second"
kind = "attached"
path = "{second_tree}"
""",
    )
    for loc in config_mod.load_config(root).locations:
        locationindex.attest_location(root, loc)

    digest = hashing.hash_file(first_tree / "a.bin", also=())["blake3"]
    assert locationindex.route_for(root, digest) == first_tree / "a.bin"


# ---------- containment integration ---------- #


def test_ensure_local_bytes_resolves_location_resident_file(tmp_path):
    root = _corpus(tmp_path)
    tree = tmp_path / "tree"
    tree.mkdir()
    f = tree / "dataset.bin"
    data = b"some dataset bytes with no standalone artifact"
    f.write_bytes(data)
    _write_toml(
        root,
        f"""
[[corpus.location]]
name = "datasets"
kind = "attached"
path = "{tree}"
""",
    )
    loc = config_mod.load_config(root).locations[0]
    locationindex.attest_location(root, loc)

    digest = hashing.hash_file(f, also=())["blake3"]
    resolved = containment.ensure_local_bytes(root, digest, "bin")
    assert resolved == f
    assert resolved.read_bytes() == data
