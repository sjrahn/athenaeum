"""The ath umbrella: manifest loading, sync (clone/fetch), status, dispatch."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from ath._cli import main
from ath.manifest import ManifestError, find_root, load


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True)


@pytest.fixture()
def system(tmp_path: Path) -> Path:
    """A miniature system: two bare 'remotes' + an orchestrator root with a manifest."""
    remotes = tmp_path / "remotes"
    for name in ("corpus", "codex-demo"):
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
        "codices:\n"
        "  codex-demo:\n"
    )
    return root


def test_manifest_defaults(system: Path) -> None:
    members = load(system)
    assert [(m.name, m.layer) for m in members] == [
        ("corpus", "corpora"),
        ("codex-demo", "codices"),
    ]
    corpus, demo = members
    assert corpus.path == system / "corpora" / "corpus"
    assert corpus.remote.endswith("/remotes/corpus.git")
    assert corpus.description == "test hub"
    assert demo.path == system / "codices" / "codex-demo"


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
    assert (system / "codices" / "codex-demo" / "README.md").read_text() == "# codex-demo\n"
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
