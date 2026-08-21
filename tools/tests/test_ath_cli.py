"""The ath umbrella: instance-config loading, init, status, dispatch."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ath._cli import main
from ath.manifest import (
    ManifestError,
    Snapshot,
    find_root,
    load_instance,
    load_references,
)


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture()
def instance(tmp_path: Path) -> Path:
    """A miniature instance: config + corpus/ledger skeletons."""
    root = tmp_path / "instance"
    (root / "corpus" / "records").mkdir(parents=True)
    (root / "corpus" / "schema").mkdir(parents=True)
    (root / "ledger" / "facts").mkdir(parents=True)
    (root / "athenaeum.yaml").write_text(
        "name: testeum\nvisibility: private\nreferences: {}\n"
    )
    return root


def test_instance_defaults(instance: Path) -> None:
    inst = load_instance(instance)
    assert inst.name == "testeum"
    assert inst.visibility == "private"
    assert inst.corpus_root == instance / "corpus"
    assert inst.ledger_root == instance / "ledger"


def test_instance_visibility_validated(tmp_path: Path) -> None:
    (tmp_path / "athenaeum.yaml").write_text("visibility: sorta\n")
    with pytest.raises(ManifestError, match="visibility"):
        load_instance(tmp_path)


def test_instance_tenancy_absent_is_the_binary(instance: Path) -> None:
    """No `tenancy:` block: tiers/audiences empty, `declared_tiers` is exactly
    the reserved pair, an unknown audience name grants only `public` — the
    pre-tier instance, byte-identically (spec/ledger.md §6.4)."""
    inst = load_instance(instance)
    assert inst.tiers == ()
    assert inst.audiences == {}
    assert inst.declared_tiers == frozenset({"public", "private"})
    assert inst.grants_for("family") == frozenset({"public"})


def test_instance_tenancy_happy_path(tmp_path: Path) -> None:
    (tmp_path / "athenaeum.yaml").write_text(
        "visibility: family\n"
        "tenancy:\n"
        "  tiers: [family, accountant]\n"
        "  audiences:\n"
        "    family: [family]\n"
        "    finances: [accountant]\n"
    )
    inst = load_instance(tmp_path)
    assert inst.tiers == ("family", "accountant")
    assert inst.visibility == "family"
    assert inst.declared_tiers == frozenset({"public", "private", "family", "accountant"})
    assert inst.audiences == {"family": ("family",), "finances": ("accountant",)}
    assert inst.grants_for("family") == frozenset({"public", "family"})
    assert inst.grants_for("finances") == frozenset({"public", "accountant"})


def test_instance_tenancy_tier_collides_with_reserved(tmp_path: Path) -> None:
    (tmp_path / "athenaeum.yaml").write_text("tenancy:\n  tiers: [public]\n")
    with pytest.raises(ManifestError, match="reserved"):
        load_instance(tmp_path)


def test_instance_tenancy_duplicate_tier(tmp_path: Path) -> None:
    (tmp_path / "athenaeum.yaml").write_text("tenancy:\n  tiers: [family, family]\n")
    with pytest.raises(ManifestError, match="duplicate tier"):
        load_instance(tmp_path)


def test_instance_tenancy_bad_tier_slug(tmp_path: Path) -> None:
    (tmp_path / "athenaeum.yaml").write_text("tenancy:\n  tiers: [Not_A_Slug]\n")
    with pytest.raises(ManifestError, match="not a slug"):
        load_instance(tmp_path)


def test_instance_tenancy_duplicate_audience(tmp_path: Path) -> None:
    """A YAML mapping can't repeat a key verbatim, but a bare `1` and a
    quoted `'1'` are distinct YAML keys that both stringify to `"1"` —
    exercising the post-stringification duplicate guard."""
    (tmp_path / "athenaeum.yaml").write_text(
        "tenancy:\n  tiers: [family]\n  audiences:\n    1: [family]\n    '1': [family]\n"
    )
    with pytest.raises(ManifestError, match="duplicate audience"):
        load_instance(tmp_path)


def test_instance_tenancy_audience_cannot_grant_private(tmp_path: Path) -> None:
    (tmp_path / "athenaeum.yaml").write_text(
        "tenancy:\n  tiers: [family]\n  audiences:\n    family: [private]\n"
    )
    with pytest.raises(ManifestError, match="never grantable"):
        load_instance(tmp_path)


@pytest.mark.parametrize("name", ["public", "private", "owner"])
def test_instance_tenancy_audience_name_reserved(tmp_path: Path, name: str) -> None:
    """An audience named after a plane would shadow it at token resolution
    on the read surface (Part I §5.1) — `owner` especially: its token would
    pass the owner gate carrying only tier grants."""
    (tmp_path / "athenaeum.yaml").write_text(
        f"tenancy:\n  tiers: [family]\n  audiences:\n    {name}: [family]\n"
    )
    with pytest.raises(ManifestError, match="reserved"):
        load_instance(tmp_path)


def test_instance_tenancy_audience_undeclared_tier(tmp_path: Path) -> None:
    (tmp_path / "athenaeum.yaml").write_text(
        "tenancy:\n  audiences:\n    family: [family]\n"
    )
    with pytest.raises(ManifestError, match="not a declared tier"):
        load_instance(tmp_path)


def test_instance_tenancy_unknown_key(tmp_path: Path) -> None:
    (tmp_path / "athenaeum.yaml").write_text("tenancy:\n  bogus: 1\n")
    with pytest.raises(ManifestError, match="unknown keys"):
        load_instance(tmp_path)


def test_instance_visibility_names_a_declared_tier(tmp_path: Path) -> None:
    """`visibility:` generalizes past the binary: any declared tier is
    admissible, an undeclared name is still refused (spec/ledger.md §6.4)."""
    (tmp_path / "athenaeum.yaml").write_text(
        "visibility: family\ntenancy:\n  tiers: [family]\n"
    )
    assert load_instance(tmp_path).visibility == "family"
    (tmp_path / "athenaeum.yaml").write_text("visibility: nope\n")
    with pytest.raises(ManifestError, match="declared tier"):
        load_instance(tmp_path)


def test_pre_v26_member_manifest_refused(tmp_path: Path) -> None:
    """A member-shaped manifest (the pre-v26 workspace) errors with a
    migration pointer rather than silently misreading."""
    (tmp_path / "athenaeum.yaml").write_text(
        "org: https://x\ncorpora:\n  corpus:\nledger:\n  ledger:\n"
    )
    with pytest.raises(ManifestError, match="v26"):
        load_instance(tmp_path)
    with pytest.raises(ManifestError, match="v26"):
        load_references(tmp_path)


_H1 = "1" * 64
_H2 = "2" * 64


def _write_references(tmp_path: Path, body: str) -> None:
    (tmp_path / "athenaeum.yaml").write_text(f"references:\n{body}")


def test_manifest_references(tmp_path: Path) -> None:
    """Multi-snapshot shape (spec Part I §2.3): adapter, latest, a tag-keyed
    snapshots map of blake3 mirror-artifact hashes; an optional per-snapshot
    `path:` materialization override (deprecated, read tolerantly)."""
    _write_references(
        tmp_path,
        "  wikipedia:\n"
        "    description: English Wikipedia, ZIM mirror\n"
        "    adapter: zim\n"
        "    latest: '2026-06'\n"
        "    snapshots:\n"
        f"      '2026-06': {{ artifact: {_H1}, path: /mnt/mirrors/wp.zim }}\n"
        f"      '2026-01': {{ artifact: {_H2} }}\n",
    )
    (ref,) = load_references(tmp_path)
    assert ref.dataset == "wikipedia"
    assert ref.adapter == "zim"
    assert ref.latest == "2026-06"
    assert ref.snapshots == {
        "2026-06": Snapshot(artifact=_H1, path="/mnt/mirrors/wp.zim"),
        "2026-01": Snapshot(artifact=_H2),
    }
    assert ref.snapshots["2026-01"].path is None
    (tmp_path / "athenaeum.yaml").write_text("references: {}\n")
    assert load_references(tmp_path) == []
    (tmp_path / "athenaeum.yaml").write_text("name: x\n")
    assert load_references(tmp_path) == []


def test_manifest_references_retired_shape_errors(tmp_path: Path) -> None:
    """The pre-multi-snapshot `mirror:`/`snapshot:` keys are retired — the
    error names the current shape rather than failing cryptically."""
    _write_references(
        tmp_path,
        "  wikipedia:\n    mirror: /mirrors/wp.zim\n    snapshot: '2026-06'\n",
    )
    with pytest.raises(ManifestError, match="retired"):
        load_references(tmp_path)


def test_manifest_references_missing_adapter_is_optional(tmp_path: Path) -> None:
    """`adapter:` is optional — derived at resolution time from the mirror
    record's mime overlay `ref_adapter` (refdata.resolve_adapter_name); loading
    just records the absence."""
    _write_references(
        tmp_path,
        f"  wikipedia:\n    latest: t\n    snapshots:\n      t: {{ artifact: {_H1} }}\n",
    )
    (ref,) = load_references(tmp_path)
    assert ref.adapter is None


def test_manifest_references_missing_snapshots(tmp_path: Path) -> None:
    _write_references(tmp_path, "  wikipedia:\n    adapter: zim\n    latest: t\n")
    with pytest.raises(ManifestError, match="snapshots"):
        load_references(tmp_path)


def test_manifest_references_latest_must_name_a_snapshot(tmp_path: Path) -> None:
    _write_references(
        tmp_path,
        f"  wikipedia:\n    adapter: zim\n    latest: nope\n    snapshots:\n"
        f"      t: {{ artifact: {_H1} }}\n",
    )
    with pytest.raises(ManifestError, match="latest"):
        load_references(tmp_path)


def test_manifest_references_bad_artifact_hash(tmp_path: Path) -> None:
    _write_references(
        tmp_path,
        "  wikipedia:\n    adapter: zim\n    latest: t\n    snapshots:\n"
        "      t: { artifact: not-a-hash }\n",
    )
    with pytest.raises(ManifestError, match="blake3"):
        load_references(tmp_path)


def test_manifest_references_bad_tag_charset(tmp_path: Path) -> None:
    """Tags ride in `ref://` URIs after `@` — `/` and `@` must be impossible."""
    _write_references(
        tmp_path,
        "  wikipedia:\n    adapter: zim\n    latest: 'bad/tag'\n    snapshots:\n"
        f"      'bad/tag': {{ artifact: {_H1} }}\n",
    )
    with pytest.raises(ManifestError, match="\\^\\[a-z0-9\\]"):
        load_references(tmp_path)


def test_find_root_walks_up(instance: Path) -> None:
    deep = instance / "corpus" / "somewhere" / "deep"
    deep.mkdir(parents=True)
    assert find_root(deep) == instance
    with pytest.raises(ManifestError, match=r"no athenaeum\.yaml"):
        find_root(instance.parent)


def test_find_root_env_override(instance: Path, monkeypatch: pytest.MonkeyPatch,
                                tmp_path: Path) -> None:
    monkeypatch.setenv("ATHENAEUM_ROOT", str(instance))
    assert find_root() == instance
    monkeypatch.setenv("ATHENAEUM_ROOT", str(tmp_path / "nowhere"))
    with pytest.raises(ManifestError, match="ATHENAEUM_ROOT"):
        find_root()


def test_init_scaffolds_instance(tmp_path: Path,
                                 capsys: pytest.CaptureFixture[str]) -> None:
    target = tmp_path / "fresh"
    assert main(["init", str(target), "--name", "fresh"]) == 0
    inst = load_instance(target)
    assert inst.name == "fresh"
    assert (target / "corpus" / "records").is_dir()
    assert (target / "corpus" / "runbooks").is_dir()
    assert (target / "ledger" / "facts" / "SCHEMA.md").is_file()
    assert (target / "ledger" / "open-questions.md").is_file()
    assert (target / "CLAUDE.md").read_text().startswith("# fresh")
    assert (target / ".claude" / "agents" / "normalizer.md").is_file()
    assert (target / ".gitignore").is_file()
    capsys.readouterr()
    # idempotent: re-run keeps existing files
    assert main(["init", str(target)]) == 0
    out = capsys.readouterr().out
    assert "kept" in out and "created" not in out.split("instance ready")[0].split("kept")[0]


def test_status_reports_instance(instance: Path,
                                 capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["status", "--root", str(instance)]) == 0
    out = capsys.readouterr().out
    assert "corpus: ok" in out and "ledger: ok" in out
    assert "visibility floor: private" in out
    # a missing layer is a non-zero exit
    (instance / "ledger" / "facts").rmdir()
    assert main(["status", "--root", str(instance)]) == 1
    assert "ledger: MISSING" in capsys.readouterr().out


def test_unknown_command() -> None:
    assert main(["bogus"]) == 2


def test_help_and_corpus_shim(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: ath" in capsys.readouterr().out
    assert main(["corpus", "--help"]) == 0
    assert "corpus" in capsys.readouterr().out
