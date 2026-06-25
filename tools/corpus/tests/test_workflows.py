"""Operating-mode runbooks (`corpus workflow`).

Guidance for *running* the tooling — the normalize loop's modes, the queue's result
lifecycle — shipped as package-data markdown so it versions with the tooling and is
maintained centrally, not per corpus. The command needs no corpus root.
"""

from __future__ import annotations

import json

from corpus import workflows
from corpus._cli import dispatch

# ---------- library ---------- #


def test_normalize_loop_is_packaged():
    names = {w.name: w for w in workflows.list_workflows()}
    assert "normalize-loop" in names
    assert names["normalize-loop"].summary  # one-liner for the index


def test_get_parses_title_and_sections():
    wf = workflows.get("normalize-loop")
    assert wf is not None
    assert wf.title == "Normalize loop"
    slugs = [s.slug for s in workflows.sections(wf.body)]
    assert slugs == ["scheduled", "standing", "results"]  # the narrowable modes + lifecycle


def test_get_unknown_is_none():
    assert workflows.get("does-not-exist") is None


def test_intro_precedes_first_section():
    wf = workflows.get("normalize-loop")
    intro = workflows.intro(wf.body)
    assert intro.startswith("# Normalize loop")
    assert "## Scheduled" not in intro  # intro stops at the first section


# ---------- CLI ---------- #


def test_cli_lists_workflows(capsys):
    assert dispatch(["workflow"]) == 0
    assert "normalize-loop" in capsys.readouterr().out


def test_cli_overview_shows_sections(capsys):
    assert dispatch(["workflow", "normalize-loop"]) == 0
    out = capsys.readouterr().out
    assert "scheduled" in out and "standing" in out and "results" in out


def test_cli_narrows_to_a_section(capsys):
    assert dispatch(["workflow", "normalize-loop", "standing"]) == 0
    out = capsys.readouterr().out
    assert "## Standing" in out
    assert "drain --wait" in out


def test_cli_section_prefix_match(capsys):
    assert dispatch(["workflow", "normalize-loop", "sched"]) == 0
    assert "## Scheduled" in capsys.readouterr().out


def test_cli_full_prints_whole_runbook(capsys):
    assert dispatch(["workflow", "normalize-loop", "--full"]) == 0
    out = capsys.readouterr().out
    assert "# Normalize loop" in out and "## Results" in out


def test_cli_json_index_is_machine_readable(capsys):
    assert dispatch(["workflow", "--json"]) == 0
    data = json.loads(capsys.readouterr().out)
    assert any(w["name"] == "normalize-loop" for w in data)


def test_cli_unknown_workflow_exits_2(capsys):
    assert dispatch(["workflow", "nope"]) == 2
    assert "no workflow" in capsys.readouterr().err


def test_cli_unknown_section_exits_2(capsys):
    assert dispatch(["workflow", "normalize-loop", "bogus"]) == 2
    assert "no section" in capsys.readouterr().err
