"""The `promote` need action (spec/ledger.md §6.3, §7.2): where the needed
evidence surface is a container *member*, the demand is `corpus promote`, not
"normalize the container." A promote need's `record` is a member functional
URI (`corpus://<hash>?<member-address>`) — never a bare corpus:// record,
since a bare hash names no member (`corpus promote` itself refuses one).

New module — not folded into test_ledger_check.py — to avoid colliding with
parallel work on that file; it reuses that file's `system` fixture and
authoring sugar rather than duplicating the corpus/ledger scaffolding.
"""

from __future__ import annotations

from pathlib import Path

from ledger.model import NEED_ACTIONS, load_json_dir
from ledger.views import render_worklist
from tests.test_ledger_check import H_PUB, _check, _interp, _regen
from tests.test_ledger_check import system as system  # re-exported pytest fixture

MEMBER_URI = f"corpus://{H_PUB}?path=Takeout/Mail/foo.mbox"


def _assessment(root: Path, iid: str, needs: list[dict]) -> None:
    _interp(root, {
        "id": iid, "kind": "assessment", "about": [],
        "statement": "s", "reasoning": "r", "based_on": [f"corpus://{H_PUB}"],
        "needs": needs, "status": "standing", "asof": "2026-07-02",
    })


def test_promote_is_a_known_need_action() -> None:
    assert "promote" in NEED_ACTIONS


def test_promote_need_with_member_uri_passes(system: Path) -> None:
    _assessment(system, "gap", [
        {"action": "promote", "record": MEMBER_URI,
         "why": "the receipt lives as a container member, not yet a standalone record"},
    ])
    _regen(system)
    rep = _check(system)
    assert rep.errors == []
    assert rep.warnings == []


def test_promote_need_requires_member_address(system: Path) -> None:
    _assessment(system, "bare", [
        {"action": "promote", "record": f"corpus://{H_PUB}", "why": "no member address"},
    ])
    rep = _check(system)
    assert any("promote need requires a member" in e for e in rep.errors)


def test_unknown_need_action_still_errors(system: Path) -> None:
    _assessment(system, "bogus", [
        {"action": "normalize", "why": "not a real need action"},
    ])
    rep = _check(system)
    assert any("bad need action" in e for e in rep.errors)


def test_worklist_renders_promote_need(system: Path) -> None:
    _assessment(system, "gap2", [
        {"action": "promote", "record": MEMBER_URI, "why": "promote the mbox member"},
    ])
    _regen(system)
    openq = (system / "ledger" / "open-questions.md").read_text()
    assert "(promote)" in openq
    assert H_PUB[:12] in openq


def test_render_worklist_directly_includes_promote_need(system: Path) -> None:
    _assessment(system, "gap3", [
        {"action": "promote", "record": MEMBER_URI, "why": "promote the mbox member"},
    ])
    facts, _ = load_json_dir(system / "ledger", "facts/*/*.json")
    interps, _ = load_json_dir(system / "ledger", "interpretations/*.json")
    block = render_worklist(system / "ledger", facts, interps, {})
    assert "(promote)" in block
