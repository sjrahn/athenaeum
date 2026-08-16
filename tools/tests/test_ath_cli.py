"""The ath umbrella: manifest loading, sync (clone/fetch), status, dispatch."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ath._cli import main
from ath.manifest import ManifestError, Snapshot, find_root, load, load_references


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture()
def system(tmp_path: Path) -> Path:
    """A miniature system: two bare 'remotes' + an orchestrator root with a manifest."""
    remotes = tmp_path / "remotes"
    for name in ("corpus", "ledger"):
        bare = remotes / f"{name}.git"
        bare.mkdir(parents=True)
        _git(bare, "init", "--bare", "--initial-branch=main", ".")
        work = tmp_path / f"seed-{name}"
        work.mkdir()
        _git(work, "init", "--initial-branch=main", ".")
        _git(work, "config", "user.email", "t@t")
        _git(work, "config", "user.name", "t")
        (work / "README.md").write_text(f"# {name}\n")
        _git(work, "add", "-A")
        _git(work, "commit", "-m", "seed")
        _git(work, "remote", "add", "origin", str(bare))
        _git(work, "push", "-q", "origin", "main")
    root = tmp_path / "athenaeum"
    root.mkdir()
    (root / "athenaeum.yaml").write_text(
        f"org: {remotes.as_uri()}\n"
        "corpora:\n"
        "  corpus:\n"
        "    description: test hub\n"
        "ledger:\n"
        "  ledger:\n"
        "    description: test ledger\n"
    )
    return root


def test_manifest_defaults(system: Path) -> None:
    members = load(system)
    assert [(m.name, m.layer) for m in members] == [
        ("corpus", "corpora"),
        ("ledger", "ledger"),
    ]
    corpus, ledger = members
    assert corpus.path == system / "corpora" / "corpus"
    assert corpus.remote.endswith("/remotes/corpus.git")
    assert corpus.description == "test hub"
    assert ledger.path == system / "ledger"  # the ledger sits at the workspace root


def test_manifest_exactly_one_ledger(tmp_path: Path) -> None:
    (tmp_path / "athenaeum.yaml").write_text(
        "org: https://x\nledger:\n  ledger:\n  ledger-two:\n"
    )
    with pytest.raises(ManifestError, match="exactly one ledger"):
        load(tmp_path)


_H1 = "1" * 64
_H2 = "2" * 64


def _write_references(tmp_path: Path, body: str) -> None:
    (tmp_path / "athenaeum.yaml").write_text(f"org: https://x\nreferences:\n{body}")


def test_manifest_references(tmp_path: Path) -> None:
    """*(v17, spec/athenaeum.md §2.3)* multi-snapshot shape: adapter, latest,
    a tag-keyed snapshots map of blake3 mirror-artifact hashes. *(v18)* an
    optional per-snapshot `path:` materialization override."""
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
    (tmp_path / "athenaeum.yaml").write_text("org: https://x\nreferences: {}\n")
    assert load_references(tmp_path) == []
    (tmp_path / "athenaeum.yaml").write_text("org: https://x\n")
    assert load_references(tmp_path) == []


def test_manifest_references_retired_shape_errors(tmp_path: Path) -> None:
    """The pre-v17 `mirror:`/`snapshot:` keys are retired — the error names
    the v17 shape rather than failing silently or cryptically."""
    _write_references(
        tmp_path,
        "  wikipedia:\n    mirror: /mirrors/wp.zim\n    snapshot: '2026-06'\n",
    )
    with pytest.raises(ManifestError, match="v17"):
        load_references(tmp_path)


def test_manifest_references_missing_adapter(tmp_path: Path) -> None:
    _write_references(
        tmp_path,
        f"  wikipedia:\n    latest: t\n    snapshots:\n      t: {{ artifact: {_H1} }}\n",
    )
    with pytest.raises(ManifestError, match="adapter"):
        load_references(tmp_path)


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


def test_manifest_overrides_and_errors(tmp_path: Path) -> None:
    root = tmp_path
    (root / "athenaeum.yaml").write_text(
        "corpora:\n  c1:\n    path: elsewhere/c1\n    remote: https://x/c1.git\n"
    )
    (m,) = load(root)
    assert m.path == root / "elsewhere" / "c1"
    assert m.remote == "https://x/c1.git"
    (root / "athenaeum.yaml").write_text("corpora:\n  c1:\n")  # no remote, no org
    with pytest.raises(ManifestError, match="no remote"):
        load(root)


def test_find_root_walks_up(system: Path) -> None:
    deep = system / "corpora" / "somewhere" / "deep"
    deep.mkdir(parents=True)
    assert find_root(deep) == system
    with pytest.raises(ManifestError, match=r"no athenaeum\.yaml"):
        find_root(system.parent)


def test_sync_clones_then_reports(system: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["sync", "--root", str(system)]) == 0
    assert (system / "corpora" / "corpus" / ".git").exists()
    assert (system / "ledger" / "README.md").read_text() == "# ledger\n"
    capsys.readouterr()
    assert main(["sync", "--root", str(system)]) == 0  # idempotent
    out = capsys.readouterr().out
    assert "corpus: ok (↑0 ↓0)" in out


def test_sync_pull_fast_forwards(system: Path) -> None:
    assert main(["sync", "--root", str(system)]) == 0
    # advance the remote from a second clone
    other = system.parent / "other"
    subprocess.run(
        ["git", "clone", "-q", (system.parent / "remotes" / "corpus.git").as_uri(), str(other)],
        check=True,
    )
    _git(other, "config", "user.email", "t@t")
    _git(other, "config", "user.name", "t")
    (other / "new.txt").write_text("x\n")
    _git(other, "add", "-A")
    _git(other, "commit", "-m", "advance")
    _git(other, "push", "-q", "origin", "main")
    assert main(["sync", "--root", str(system), "--pull"]) == 0
    assert (system / "corpora" / "corpus" / "new.txt").exists()


def test_status_missing_then_clean(system: Path, capsys: pytest.CaptureFixture[str]) -> None:
    # the orchestrator root itself is not a git repo in this fixture → MISSING row
    assert main(["status", "--root", str(system)]) == 1
    out = capsys.readouterr().out
    assert out.count("MISSING") == 3  # root + 2 members
    _git(system, "init", "--initial-branch=main", ".")
    assert main(["sync", "--root", str(system)]) == 0
    capsys.readouterr()
    assert main(["status", "--root", str(system)]) == 0
    out = capsys.readouterr().out
    assert "corpus" in out and "clean" in out


def test_unknown_command() -> None:
    assert main(["bogus"]) == 2


def test_help_and_corpus_shim(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([]) == 0
    assert "usage: ath" in capsys.readouterr().out
    assert main(["corpus", "--help"]) == 0
    assert "corpus" in capsys.readouterr().out
