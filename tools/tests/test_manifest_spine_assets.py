"""`athenaeum.yaml` config parsing for the v39 additions (spec/athenaeum.md
§2.3, spec/ledger.md §15.2): the `references:` entry's optional `spine: true`
flag, and the new `assets:` top-level section — the same tag-keyed
`snapshots:`/`latest:` grammar as `references:`, none of its adapter/citation
semantics.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from ath.manifest import ManifestError, load_assets, load_references

_ARTIFACT = "a" * 64
_ARTIFACT2 = "b" * 64


def _write(root: Path, text: str) -> None:
    (root / "athenaeum.yaml").write_text(text, encoding="utf-8")


# --- references: spine: true -------------------------------------------


def test_reference_spine_flag_defaults_false(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"""\
references:
  cco:
    description: CCO
    adapter: cco-release
    latest: t
    snapshots:
      t:
        artifact: "{_ARTIFACT}"
""",
    )
    refs = load_references(tmp_path)
    assert len(refs) == 1
    assert refs[0].spine is False


def test_reference_spine_flag_true(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"""\
references:
  cco:
    description: CCO
    adapter: cco-release
    spine: true
    latest: t
    snapshots:
      t:
        artifact: "{_ARTIFACT}"
""",
    )
    refs = load_references(tmp_path)
    assert refs[0].spine is True


def test_reference_spine_flag_non_boolean_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"""\
references:
  cco:
    description: CCO
    adapter: cco-release
    spine: "yes"
    latest: t
    snapshots:
      t:
        artifact: "{_ARTIFACT}"
""",
    )
    with pytest.raises(ManifestError, match="spine must be a boolean"):
        load_references(tmp_path)


# --- assets: ---------------------------------------------------------------


def test_assets_valid_shape_parses(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"""\
assets:
  singlefile:
    description: SingleFile capture bundle
    latest: v1
    snapshots:
      v1:
        artifact: "{_ARTIFACT}"
""",
    )
    assets = load_assets(tmp_path)
    assert len(assets) == 1
    a = assets[0]
    assert a.name == "singlefile"
    assert a.description == "SingleFile capture bundle"
    assert a.latest == "v1"
    assert a.snapshots["v1"].artifact == _ARTIFACT


def test_assets_multi_snapshot_and_tag_pin_shape(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"""\
assets:
  singlefile:
    description: SingleFile capture bundle
    latest: v2
    snapshots:
      v1:
        artifact: "{_ARTIFACT}"
      v2:
        artifact: "{_ARTIFACT2}"
""",
    )
    assets = load_assets(tmp_path)
    a = assets[0]
    assert a.latest == "v2"
    assert set(a.snapshots) == {"v1", "v2"}


def test_assets_no_entries_is_empty_list(tmp_path: Path) -> None:
    _write(tmp_path, "name: test\n")
    assert load_assets(tmp_path) == []


def test_assets_not_a_mapping_rejected(tmp_path: Path) -> None:
    _write(tmp_path, "assets: [not, a, mapping]\n")
    with pytest.raises(ManifestError, match="expected a name-keyed mapping"):
        load_assets(tmp_path)


def test_assets_unknown_key_rejected(tmp_path: Path) -> None:
    """Assets carry no adapter/citation semantics — an `adapter:` (or
    `spine:`) key under an asset entry is a load-time error, not silently
    ignored."""
    _write(
        tmp_path,
        f"""\
assets:
  singlefile:
    description: x
    adapter: zim
    latest: v1
    snapshots:
      v1:
        artifact: "{_ARTIFACT}"
""",
    )
    with pytest.raises(ManifestError, match="unknown keys"):
        load_assets(tmp_path)


def test_assets_missing_snapshots_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """\
assets:
  singlefile:
    description: x
    latest: v1
""",
    )
    with pytest.raises(ManifestError, match="snapshots must be a non-empty"):
        load_assets(tmp_path)


def test_assets_bad_tag_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"""\
assets:
  singlefile:
    description: x
    latest: "Bad Tag"
    snapshots:
      "Bad Tag":
        artifact: "{_ARTIFACT}"
""",
    )
    with pytest.raises(ManifestError, match="snapshot tag"):
        load_assets(tmp_path)


def test_assets_bad_artifact_rejected(tmp_path: Path) -> None:
    _write(
        tmp_path,
        """\
assets:
  singlefile:
    description: x
    latest: v1
    snapshots:
      v1:
        artifact: "not-a-blake3"
""",
    )
    with pytest.raises(ManifestError, match="must be a 64-hex"):
        load_assets(tmp_path)


def test_assets_latest_must_name_a_snapshot_key(tmp_path: Path) -> None:
    _write(
        tmp_path,
        f"""\
assets:
  singlefile:
    description: x
    latest: v2
    snapshots:
      v1:
        artifact: "{_ARTIFACT}"
""",
    )
    with pytest.raises(ManifestError, match="latest 'v2' must name a key"):
        load_assets(tmp_path)


def test_assets_path_override_supported(tmp_path: Path) -> None:
    """Same deprecated `path:` override grammar as references' snapshots
    (shared `_parse_snapshots` helper)."""
    _write(
        tmp_path,
        f"""\
assets:
  singlefile:
    description: x
    latest: v1
    snapshots:
      v1:
        artifact: "{_ARTIFACT}"
        path: /opt/vendor/singlefile.js
""",
    )
    assets = load_assets(tmp_path)
    assert assets[0].snapshots["v1"].path == "/opt/vendor/singlefile.js"
