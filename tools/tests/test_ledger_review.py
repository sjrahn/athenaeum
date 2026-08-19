"""The merge-review page — `ath ledger dedupe --review` (#182)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger._cli import main as ledger_main
from ledger.dedupe import propose
from ledger.review import render_review

H1 = "a" * 64


def _fact(root: Path, type_: str, obj: dict) -> Path:
    p = root / "facts" / type_ / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


@pytest.fixture()
def ledger(tmp_path: Path) -> Path:
    (tmp_path / "facts").mkdir()
    (tmp_path / "interpretations").mkdir()
    return tmp_path


@pytest.fixture()
def system(tmp_path: Path) -> Path:
    """Mirrors test_ledger_dedupe.py's `system` fixture — a full manifest
    `_system()` can resolve through."""
    root = tmp_path
    (root / "athenaeum.yaml").write_text("visibility: public\n")
    (root / "corpus" / "records").mkdir(parents=True)
    ledger_dir = root / "ledger"
    (ledger_dir / "facts").mkdir(parents=True)
    (ledger_dir / "interpretations").mkdir()
    return root


# --------------------------------------------------------------------- render


def test_page_contains_names_quote_hash_and_group_number(ledger: Path) -> None:
    _fact(ledger, "person", {
        "id": "aaa", "type": "person", "name": "Alpha Alberts",
        "sources": {"s1": {"record": H1}},
        "claims": [{
            "id": "aaa:c1", "predicate": "phone", "value": "555-0000",
            "status": "provisional",
            "evidence": [{"source": "s1", "quote": "hello there", "note": "greeting"}],
        }],
    })
    _fact(ledger, "person", {"id": "aaa-friend", "type": "person", "name": "Friend of Alpha"})

    report = propose(ledger)
    assert len(report["concepts"]) == 1  # sanity: exactly the id-containment pair
    page = render_review(ledger, report)

    assert "Alpha Alberts" in page
    assert "Friend of Alpha" in page
    assert "hello there" in page
    assert H1[:8] in page
    assert "#1 " in page


def test_adjudicated_group_sorts_after_open_and_keeps_number(ledger: Path) -> None:
    _fact(ledger, "person", {"id": "bob", "type": "person", "name": "Bob"})
    _fact(ledger, "person", {"id": "bob2", "type": "person", "name": "Bob"})
    _fact(ledger, "person", {
        "id": "carl", "type": "person", "name": "Carl One",
        "meta": "distinct from carl-two, unrelated household member",
    })
    _fact(ledger, "person", {"id": "carl-two", "type": "person", "name": "Carl Two"})

    report = propose(ledger)
    concepts = report["concepts"]
    open_group = next(c for c in concepts if c["basis"] == "name-collision")
    adjudicated_group = next(c for c in concepts if c["basis"] == "id-containment")
    open_n = concepts.index(open_group) + 1
    adjudicated_n = concepts.index(adjudicated_group) + 1

    page = render_review(ledger, report)
    assert "adjudicated — see meta" in page
    assert page.index(f"#{open_n} ") < page.index(f"#{adjudicated_n} ")
    # the adjudicated group's own number is unchanged (not renumbered to 1)
    assert f"#{adjudicated_n} " in page


def test_html_escaping_of_untrusted_name(ledger: Path) -> None:
    payload = "<script>alert(1)</script>"
    _fact(ledger, "person", {"id": "x", "type": "person", "name": payload})
    _fact(ledger, "person", {"id": "x2", "type": "person", "name": payload})

    report = propose(ledger)
    page = render_review(ledger, report)
    assert payload not in page
    assert "&lt;script&gt;" in page


def test_dict_value_clipped(ledger: Path) -> None:
    big = {"k": "v" * 300}
    _fact(ledger, "person", {
        "id": "y", "type": "person", "name": "Y",
        "claims": [{"id": "y:c1", "predicate": "model_numbers", "value": big,
                    "status": "provisional"}],
    })
    _fact(ledger, "person", {"id": "y2", "type": "person", "name": "Y"})

    report = propose(ledger)
    page = render_review(ledger, report)
    assert "…" in page
    assert ("v" * 300) not in page


def test_missing_fact_file_yields_error_card_not_exception(ledger: Path) -> None:
    _fact(ledger, "person", {"id": "known", "type": "person", "name": "Known"})
    proposal = {"concepts": [{"basis": "name-collision", "key": "x",
                              "ids": ["known", "ghost"]}]}
    page = render_review(ledger, proposal)  # must not raise
    assert "ghost" in page
    assert "not found or unreadable" in page


def test_empty_concepts_renders_without_error(ledger: Path) -> None:
    page = render_review(ledger, {"concepts": []})
    assert "0 open" in page
    assert "0 adjudicated" in page


# ------------------------------------------------------------------------- CLI


def test_cli_review_writes_file_and_prints_path(
    system: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    ledger_dir = system / "ledger"
    _fact(ledger_dir, "part", {"id": "bcm", "type": "part", "name": "BCM"})
    _fact(ledger_dir, "part", {"id": "bcm2", "type": "part", "name": "BCM"})
    out = system / "out.html"

    rc = ledger_main(["dedupe", "--root", str(system), "--review", str(out)])
    assert rc == 0
    assert out.is_file()
    assert "<title>Merge review</title>" in out.read_text(encoding="utf-8")
    printed = capsys.readouterr().out
    assert str(out) in printed
    assert "open" in printed and "adjudicated" in printed


def test_cli_review_default_path_under_cache(system: Path) -> None:
    ledger_dir = system / "ledger"
    _fact(ledger_dir, "part", {"id": "bcm", "type": "part", "name": "BCM"})
    _fact(ledger_dir, "part", {"id": "bcm2", "type": "part", "name": "BCM"})

    rc = ledger_main(["dedupe", "--root", str(system), "--review"])
    assert rc == 0
    assert (ledger_dir / ".cache" / "dedupe-review.html").is_file()


def test_cli_review_rejects_json_combo(system: Path, capsys: pytest.CaptureFixture[str]) -> None:
    rc = ledger_main(["dedupe", "--root", str(system), "--review", "--json"])
    assert rc == 2
    assert "--review" in capsys.readouterr().err
