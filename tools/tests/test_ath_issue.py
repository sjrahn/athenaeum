"""`ath issue` — the manifest join, the snapshot renderer, and the offline path.

Nothing here touches the network. What is worth pinning is the shape of the offline
contract: the snapshot must be readable without a tracker, and `--check` must FAIL when it
has drifted, because a stale snapshot that reports success is worse than no snapshot — it
would boot a session on a backlog that has moved.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from ath._cli.issue import _counts, _is_tombstone, _labels, _read_snapshot_titles, _render_snapshot
from ath.manifest import ManifestError, load_tracker

MANIFEST = textwrap.dedent(
    """\
    org: https://code.example.test/athenaeum
    tracker:
      repo: athenaeum/athenaeum
      snapshot: books/tickets.md
    corpora:
      corpus:
        visibility: public
    ledger:
      ledger: {}
    codices: {}
    """
)


def _root(tmp_path: Path, manifest: str = MANIFEST) -> Path:
    tmp_path.joinpath("athenaeum.yaml").write_text(manifest, encoding="utf-8")
    return tmp_path


def _issue(number, title, state="open", labels=(), url=None):
    return {
        "number": number,
        "title": title,
        "state": state,
        "labels": [{"name": n} for n in labels],
        "html_url": url or f"https://code.example.test/athenaeum/athenaeum/issues/{number}",
    }


def test_the_host_comes_from_org_so_no_instance_is_hardcoded(tmp_path):
    t = load_tracker(_root(tmp_path))
    assert t.base == "https://code.example.test/api/v1"
    assert t.owner == "athenaeum" and t.repo == "athenaeum"
    assert t.issues_path == "/repos/athenaeum/athenaeum/issues"
    # the web URL is the API root minus the API suffix — not a second spelling of the host
    assert t.web == "https://code.example.test/athenaeum/athenaeum/issues"
    assert t.snapshot == tmp_path / "books/tickets.md"


def test_snapshot_defaults_into_docs(tmp_path):
    root = _root(tmp_path, "org: https://h.test/o\ntracker:\n  repo: o/r\n")
    assert load_tracker(root).snapshot.name == "tickets.md"
    assert load_tracker(root).snapshot.parent.name == "docs"


@pytest.mark.parametrize(
    "manifest, fragment",
    [
        ("tracker:\n  repo: o/r\n", "no org"),
        ("org: https://h.test/o\ntracker:\n  repo: justname\n", "owner/name"),
        ("org: https://h.test/o\ntracker: [nope]\n", "expected a mapping"),
    ],
)
def test_a_malformed_tracker_section_is_refused_not_guessed(tmp_path, manifest, fragment):
    with pytest.raises(ManifestError) as e:
        load_tracker(_root(tmp_path, manifest))
    assert fragment in str(e.value)


def test_tombstones_are_summarised_not_listed(tmp_path):
    """50 placeholder lines would bury the tickets that carry meaning."""
    t = load_tracker(_root(tmp_path))
    issues = [_issue(n, f"Reserved — #{n}", "closed", ["tombstone"]) for n in range(1, 4)]
    issues.append(_issue(52, "A real ticket", "open", ["layer:corpus"]))
    out = _render_snapshot(t, issues)
    assert "A real ticket" in out
    assert "Reserved" not in out
    assert "3 reserved ids not listed: #1–#3" in out
    assert "**1 open · 0 closed**" in out


def test_the_snapshot_says_the_tracker_wins(tmp_path):
    """A generated file that does not declare its own authority gets hand-edited."""
    t = load_tracker(_root(tmp_path))
    out = _render_snapshot(t, [_issue(52, "x")])
    assert "Do not hand-edit" in out
    assert "the tracker wins" in out
    assert t.web in out


def test_open_and_closed_are_separated_and_open_carries_labels(tmp_path):
    t = load_tracker(_root(tmp_path))
    out = _render_snapshot(t, [
        _issue(52, "still open", "open", ["blocked", "layer:corpus"]),
        _issue(53, "done", "closed", ["layer:spec"]),
    ])
    open_section = out.split("## Closed")[0]
    assert "still open" in open_section and "done" not in open_section
    assert "`blocked`" in open_section and "`layer:corpus`" in open_section
    # a closed ticket keeps its link but not the label noise
    assert "[#53]" in out.split("## Closed")[1]


def test_counts_line_omits_the_reserved_clause_when_there_are_none():
    assert _counts([1], [2, 3], []) == "**1 open · 2 closed**"
    assert "reserved" in _counts([1], [], [4, 9])


def test_labels_are_sorted_so_the_snapshot_does_not_churn():
    assert _labels(_issue(1, "t", labels=["zeta", "alpha"])) == ["alpha", "zeta"]
    assert _is_tombstone(_issue(1, "t", labels=["tombstone"]))
    assert not _is_tombstone(_issue(1, "t", labels=["layer:corpus"]))


def test_offline_read_returns_the_bullet_rows(tmp_path):
    snap = tmp_path / "tickets.md"
    snap.write_text("# Tickets\n\nprose\n\n- **[#88](u)** — a ticket\n- [#50](u) — closed one\n")
    rows = _read_snapshot_titles(snap)
    assert len(rows) == 2
    assert "#88" in rows[0]


def test_offline_read_of_a_missing_snapshot_is_empty_not_an_exception(tmp_path):
    assert _read_snapshot_titles(tmp_path / "nope.md") == []


def test_check_detects_drift(tmp_path):
    """The property that matters: a stale snapshot must not report success."""
    t = load_tracker(_root(tmp_path))
    issues = [_issue(52, "original title", "open")]
    first = _render_snapshot(t, issues)
    moved = _render_snapshot(t, [_issue(52, "retitled", "open")])
    assert first != moved

    closed_now = _render_snapshot(t, [_issue(52, "original title", "closed")])
    assert first != closed_now, "a ticket closing must change the snapshot"
