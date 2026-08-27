"""The `ath ledger export --gate` conformance gate (spec/ledger.md §15.7,
ISO/IEC 21838-1 Annex D.5.1): honestly unverifiable with no reasoner on
PATH, and the invoked path against a fake `robot` script that captures its
argv and exits pass/fail on command."""

from __future__ import annotations

import stat
import textwrap
from pathlib import Path

from ledger.export import GateResult, run_conformance_gate

_SAMPLE_TEXT = "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<ledger://x> a owl:Class .\n"


def _write_fake_robot(bin_dir: Path, *, exit_code: int, argv_log: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "robot"
    script.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        printf '%s\\n' "$@" > "{argv_log}"
        exit {exit_code}
    """), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_unverifiable_with_no_reasoner_on_path(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("PATH", str(tmp_path / "empty-bin"))  # deliberately no robot
    monkeypatch.delenv("ATHENAEUM_REASONER", raising=False)
    (tmp_path / "empty-bin").mkdir()
    result = run_conformance_gate(_SAMPLE_TEXT, work_dir=tmp_path / "gate")
    assert result.status == "unverifiable"
    assert "reasoner" in result.detail.lower()
    assert (tmp_path / "gate" / "export.ttl").read_text(encoding="utf-8") == _SAMPLE_TEXT


def test_invoked_path_captures_argv_and_passes(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    argv_log = tmp_path / "argv.log"
    _write_fake_robot(bin_dir, exit_code=0, argv_log=argv_log)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv("ATHENAEUM_REASONER", raising=False)

    result = run_conformance_gate(_SAMPLE_TEXT, work_dir=tmp_path / "gate")
    assert result.status == "passed"
    logged = argv_log.read_text(encoding="utf-8")
    assert "--input" in logged
    # the reasoner is handed the OWL-consumable projection, not the 1.2 text
    assert str(tmp_path / "gate" / "export-reasoner.ttl") in logged
    assert "reason" in logged


def test_invoked_path_captures_argv_and_fails(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    argv_log = tmp_path / "argv.log"
    _write_fake_robot(bin_dir, exit_code=1, argv_log=argv_log)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv("ATHENAEUM_REASONER", raising=False)

    result = run_conformance_gate(_SAMPLE_TEXT, work_dir=tmp_path / "gate")
    assert result.status == "failed"
    assert argv_log.exists()


def test_spine_paths_are_passed_as_additional_inputs(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    argv_log = tmp_path / "argv.log"
    _write_fake_robot(bin_dir, exit_code=0, argv_log=argv_log)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv("ATHENAEUM_REASONER", raising=False)

    spine_file = tmp_path / "bfo-core.owl"
    spine_file.write_text("<rdf:RDF/>", encoding="utf-8")
    result = run_conformance_gate(_SAMPLE_TEXT, work_dir=tmp_path / "gate",
                                  spine_paths=[spine_file])
    assert result.status == "passed"
    logged = argv_log.read_text(encoding="utf-8")
    assert str(spine_file) in logged


def test_reasoner_env_override_template_is_used(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    argv_log = tmp_path / "argv.log"
    marker_script = bin_dir / "my-reasoner"
    bin_dir.mkdir()
    marker_script.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        printf '%s\\n' "$@" > "{argv_log}"
        exit 0
    """), encoding="utf-8")
    marker_script.chmod(marker_script.stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.setenv("ATHENAEUM_REASONER", f"{marker_script} {{inputs}}")

    result = run_conformance_gate(_SAMPLE_TEXT, work_dir=tmp_path / "gate")
    assert result.status == "passed"
    assert argv_log.exists()


def test_result_is_a_plain_dataclass() -> None:
    r = GateResult(status="unverifiable", detail="no reasoner")
    assert r.status == "unverifiable"
    assert r.detail == "no reasoner"


def test_reasoner_invocation_error_is_unverifiable_not_a_crash(tmp_path: Path) -> None:
    result = run_conformance_gate(
        _SAMPLE_TEXT, work_dir=tmp_path / "gate", reasoner_cmd="/no/such/binary {inputs}",
    )
    assert result.status == "unverifiable"
