"""`ath ledger verify` names facts by id OR fact-file path, and a name matching no fact is
an error — it used to print a clean "0 verified … 0 errors" and exit 0, so a brief saying
`verify <path>` passed facts nothing had checked."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger._cli import main as ledger_main


@pytest.fixture()
def system(tmp_path: Path) -> Path:
    (tmp_path / "athenaeum.yaml").write_text("visibility: public\n")
    (tmp_path / "corpus" / "records").mkdir(parents=True)
    (tmp_path / "ledger" / "facts" / "part").mkdir(parents=True)
    (tmp_path / "ledger" / "interpretations").mkdir()
    (tmp_path / "ledger" / "facts" / "part" / "bcm.json").write_text(json.dumps(
        {"id": "bcm", "type": "part", "name": "Body Control Module", "claims": []}))
    return tmp_path


def test_an_id_and_a_path_both_name_the_fact(system, capsys):
    assert ledger_main(["verify", "--root", str(system), "bcm"]) == 0
    path = system / "ledger" / "facts" / "part" / "bcm.json"
    assert ledger_main(["verify", "--root", str(system), str(path)]) == 0
    assert "no fact with id" not in capsys.readouterr().err


def test_a_name_matching_no_fact_fails_loudly(system, capsys):
    assert ledger_main(["verify", "--root", str(system), "bcm", "nope"]) == 2
    assert "no fact with id nope" in capsys.readouterr().err
    missing = system / "ledger" / "facts" / "part" / "gone.json"
    assert ledger_main(["verify", "--root", str(system), str(missing)]) == 2
