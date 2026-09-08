"""`ath ledger scope` — the §12.1 library call as a shell primitive: spec in
(inline JSON, a file, or stdin), the evaluation out as JSON. The traversal
semantics themselves are `test_scope.py`'s; this covers the verb's plumbing."""

from __future__ import annotations

import io
import json
from pathlib import Path

import pytest

from ledger._cli import main as ledger_main


def _fact(ledger: Path, ftype: str, fid: str, **extra: object) -> None:
    d = ledger / "facts" / ftype
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{fid}.json").write_text(
        json.dumps({"id": fid, "type": ftype, "name": fid.title(), **extra}), encoding="utf-8"
    )


@pytest.fixture()
def instance(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "athenaeum.yaml").write_text("name: testeum\nvisibility: public\n")
    for d in ("records", "schema"):
        (root / "corpus" / d).mkdir(parents=True)
    ledger = root / "ledger"
    (ledger / "interpretations").mkdir(parents=True)
    knows = lambda who, whom: [  # noqa: E731
        {"id": f"{who}:knows", "predicate": "knows", "object": whom, "status": "confirmed"}]
    _fact(ledger, "person", "ada", claims=knows("ada", "bob"))
    _fact(ledger, "person", "bob", claims=knows("bob", "cy"))
    _fact(ledger, "person", "cy")
    _fact(ledger, "org", "acme")
    return root


def _run(capsys, argv: list[str], stdin: str | None = None,
         monkeypatch=None) -> tuple[int, str, str]:
    if stdin is not None:
        monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    rc = ledger_main(argv)
    out = capsys.readouterr()
    return rc, out.out, out.err


def test_inline_spec_prints_json_evaluation(instance: Path, capsys) -> None:
    spec = json.dumps({"seed": {"ids": ["ada"]}})
    rc, out, _ = _run(capsys, ["scope", "--root", str(instance), spec])
    assert rc == 0
    result = json.loads(out)
    assert [m["id"] for m in result["members"]] == ["ada", "bob", "cy"]
    assert {m["id"]: m["depth"] for m in result["members"]} == {"ada": 0, "bob": 1, "cy": 2}
    assert result["unknown_seeds"] == []


def test_type_seed_with_depth_and_ids_output(instance: Path, capsys) -> None:
    spec = json.dumps({"seed": {"type": "person"}, "depth": 0})
    rc, out, _ = _run(capsys, ["scope", "--root", str(instance), "--ids", spec])
    assert rc == 0
    assert out.split() == ["ada", "bob", "cy"]


def test_spec_from_file_and_stdin(instance: Path, tmp_path: Path, capsys, monkeypatch) -> None:
    spec = {"seed": {"ids": ["bob"]}, "depth": 1}
    f = tmp_path / "spec.json"
    f.write_text(json.dumps(spec))
    rc, out_file, _ = _run(capsys, ["scope", "--root", str(instance), "--ids", str(f)])
    assert rc == 0
    rc, out_stdin, _ = _run(capsys, ["scope", "--root", str(instance), "--ids", "-"],
                            stdin=json.dumps(spec), monkeypatch=monkeypatch)
    assert rc == 0
    assert out_file.split() == out_stdin.split() == ["bob", "cy"]


def test_root_from_env(instance: Path, capsys, monkeypatch) -> None:
    monkeypatch.setenv("ATHENAEUM_ROOT", str(instance))
    monkeypatch.chdir(instance.parent)
    rc, out, _ = _run(capsys, ["scope", "--ids", json.dumps({"seed": {"ids": ["cy"]}})])
    assert rc == 0
    assert out.split() == ["cy"]


@pytest.mark.parametrize("bad, needle", [
    ("{not json", "not valid JSON"),
    ('["a-list"]', "must be a JSON object"),
    ("no/such/file.json", "not a file"),
    (json.dumps({"seed": {"ids": ["ada"], "type": "person"}}), "exactly one of"),
    (json.dumps({"seed": {"ids": ["ada"]}, "follow": ["telepathy"]}), "unknown kind"),
    (json.dumps({"seed": {"ids": ["ada"]}, "evidence": "resolved"}), "read surface"),
])
def test_bad_specs_exit_2_with_message(instance: Path, capsys, bad: str, needle: str) -> None:
    rc, out, err = _run(capsys, ["scope", "--root", str(instance), bad])
    assert rc == 2
    assert out == ""
    assert needle in err


def test_scope_listed_in_usage(capsys) -> None:
    assert ledger_main(["--help"]) == 0
    assert "scope SPEC" in capsys.readouterr().out
