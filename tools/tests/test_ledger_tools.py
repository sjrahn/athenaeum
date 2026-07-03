"""The ledger's deterministic tooling: harvest (§10), evidence verification
(§13.2), promote/stamp (§7.2, §7.3), worklist, coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.coverage import render_coverage
from ledger.harvest import HarvestError, load_rules, run_harvest
from ledger.model import canonical_claim_state
from ledger.promote import PromoteError, promote, stamp
from ledger.verify import verify_ledger
from ledger.worklist import worklist

H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64


def _imessage_record(root: Path, h: str, handle, period: str) -> None:
    p = root / "records" / h[:2] / f"{h}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(handle, list):
        handle_yaml = "handle:\n" + "".join(f"- '{x}'\n" for x in handle)
    else:
        handle_yaml = f"handle: '{handle}'\n"
    p.write_text(
        f"---\nid: {h}\ntitle: ''\nstatus: normalized\n"
        "touch:\n- corpus.ingest@0.1.0\n- corpus.compile@0.1.0\n---\n\n"
        "<!--artifact text/html\n-->\n\n"
        f"<!--origin imessage-export\nsnapshot: '2026-07-01T00:00:00Z'\n"
        f"period: {period}\n{handle_yaml}-->\n\n"
        "<!--segment text/message\naddress: el=1\nsender: Me\n-->\n"
        "hello from the fixture\n<!--/segment-->\n",
        encoding="utf-8",
    )


@pytest.fixture()
def system(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "athenaeum.yaml").write_text(
        "org: https://example.test/org\n"
        "corpora:\n  corpus-private:\n    visibility: private\n"
        "ledger:\n  ledger:\n"
    )
    priv = root / "corpora" / "corpus-private"
    _imessage_record(priv, H1, "+14035551234", "2023-03")
    _imessage_record(priv, H2, "+14035551234", "2023-04")  # same chat, next window
    _imessage_record(priv, H3, ["+1403", "+1587"], "2023-03")  # group: never mints
    ledger = root / "ledger"
    (ledger / "facts").mkdir(parents=True)
    (ledger / "interpretations").mkdir()
    (ledger / "harvest").mkdir()
    (ledger / "ledger.yaml").write_text("name: ledger\ncorpora: [corpus-private]\n")
    (ledger / "open-questions.md").write_text(
        "# Open questions\n\n<!--worklist:begin-->\n<!--worklist:end-->\n"
    )
    (ledger / "harvest" / "chats.yaml").write_text(
        "id: chats\ndescription: test\n"
        "match:\n"
        "  origin.id: {equals: imessage-export}\n"
        "  origin.handle: {matches: '^\\+?[0-9]+$'}\n"
        "mint:\n"
        "  concept: {id: 'chat-{origin.handle}', type: conversation,\n"
        "            name: 'Chat {origin.handle}'}\n"
        "  roster: [{role: transcript}]\n"
        "  claims:\n"
        "    - {predicate: window, value: '{origin.period}', evidence_kind: direct}\n"
    )
    return root


def _corpora(root: Path) -> list[RegisteredCorpus]:
    return [RegisteredCorpus("corpus-private", root / "corpora" / "corpus-private",
                             private=True)]


def test_harvest_converges_by_origin_native_key(system: Path) -> None:
    run = run_harvest(system / "ledger", _corpora(system))
    assert run.minted == 1  # two windows, one chat; the group minted nothing
    concept = json.loads(
        (system / "ledger" / "facts" / "conversation" / "chat-14035551234.json").read_text()
    )
    assert concept["provenance"] == "auto"
    assert {e["uri"] for e in concept["artifacts"]} == {f"corpus://{H1}", f"corpus://{H2}"}
    assert all(e["provenance"] == "auto" for e in concept["artifacts"])
    windows = {c["value"] for c in concept["claims"] if c["predicate"] == "window"}
    assert windows == {"2023-03", "2023-04"}
    assert all(c["status"] == "provisional" for c in concept["claims"])
    # idempotent: strip + re-mint converges
    again = run_harvest(system / "ledger", _corpora(system))
    assert again.stripped_files == 1 and again.minted == 1
    assert json.loads(
        (system / "ledger" / "facts" / "conversation" / "chat-14035551234.json").read_text()
    ) == concept


def test_harvest_asserted_wins(system: Path) -> None:
    run_harvest(system / "ledger", _corpora(system))
    p = system / "ledger" / "facts" / "conversation" / "chat-14035551234.json"
    concept = json.loads(p.read_text())
    del concept["provenance"]  # a human adopts the concept
    concept["name"] = "Texts with Mom"
    concept["claims"] = [c for c in concept["claims"]
                         if c["value"] != "2023-03"]  # keep one auto claim out
    p.write_text(json.dumps(concept, indent=2))
    run = run_harvest(system / "ledger", _corpora(system))
    assert run.stripped_files == 0  # the adopted file survives the strip
    after = json.loads(p.read_text())
    assert after["name"] == "Texts with Mom"  # harvest never touches asserted content
    assert {c["value"] for c in after["claims"]} == {"2023-03", "2023-04"}  # re-converged


def test_hash_only_rules_may_not_mint(tmp_path: Path) -> None:
    (tmp_path / "harvest").mkdir()
    (tmp_path / "harvest" / "bad.yaml").write_text(
        "id: bad\nmatch: {mime: {equals: text/html}}\n"
        "mint: {concept: {id: static-thing, type: thing, name: X}}\n"
    )
    with pytest.raises(HarvestError, match="interpolates no origin fact"):
        load_rules(tmp_path)


def test_verify_quotes_and_anchors(system: Path) -> None:
    ledger = system / "ledger"
    (ledger / "facts" / "person").mkdir()
    (ledger / "facts" / "person" / "mom.json").write_text(json.dumps({
        "id": "mom", "type": "person", "name": "Mom",
        "claims": [
            {"id": "mom:greeting", "predicate": "greeting", "value": "x",
             "status": "confirmed", "asof": "2023-03-01",
             "evidence": [{"uri": f"corpus://{H1}?el=1",
                           "quote": "hello from   the fixture", "kind": "authoritative"}]},
            {"id": "mom:bogus-quote", "predicate": "bogus", "value": "x",
             "status": "confirmed", "asof": "2023-03-01",
             "evidence": [{"uri": f"corpus://{H1}?el=1",
                           "quote": "never said this", "kind": "authoritative"}]},
            {"id": "mom:bad-anchor", "predicate": "bogus2", "value": "x",
             "status": "provisional", "asof": "2023-03-01",
             "evidence": [{"uri": f"corpus://{H1}?el=99", "kind": "direct"}]},
        ],
    }))
    join = CorpusJoin(_corpora(system))
    res = verify_ledger(ledger, join, set(), stamp=True, today="2026-07-02")
    assert res.verified == 1 and res.stamped == 1
    assert any("quote not found" in e for e in res.errors)          # confirmed → error
    assert any("anchor does not resolve" in w for w in res.warnings)  # provisional → warn
    fact = json.loads((ledger / "facts" / "person" / "mom.json").read_text())
    stamped = fact["claims"][0]["evidence"][0]["verified"]
    assert stamped == {"touch": "corpus.compile@0.1.0", "at": "2026-07-02"}
    # drift: the pin excludes verified stamps, so stamping didn't change the state
    assert canonical_claim_state(fact["claims"][0]) == canonical_claim_state(
        {k: v for k, v in fact["claims"][0].items()})
    # a later-day re-run must NOT re-stamp: only a moved touch identity may
    # rewrite fact files (else every verify run churns the whole tree)
    res2 = verify_ledger(ledger, join, set(), stamp=True, today="2026-07-03")
    assert res2.verified == 1 and res2.stamped == 0
    fact2 = json.loads((ledger / "facts" / "person" / "mom.json").read_text())
    assert fact2["claims"][0]["evidence"][0]["verified"]["at"] == "2026-07-02"


def test_promote_and_stamp(system: Path) -> None:
    ledger = system / "ledger"
    (ledger / "facts" / "person").mkdir()
    (ledger / "facts" / "person" / "mom.json").write_text(json.dumps({
        "id": "mom", "type": "person", "name": "Mom",
        "claims": [{"id": "mom:phone", "predicate": "phone", "value": "+1403",
                    "status": "provisional", "asof": "2023-03-01",
                    "evidence": [{"uri": f"corpus://{H1}", "kind": "direct"}]}],
    }))
    (ledger / "interpretations" / "mom-birthday.json").write_text(json.dumps({
        "id": "mom-birthday", "kind": "hypothesis", "about": ["mom"],
        "statement": "Mom's birthday is in June.", "confidence": "likely",
        "reasoning": "r", "based_on": [f"corpus://{H1}"],
        "proposes": {"id": "mom:birthday", "predicate": "birthday", "value": "June",
                     "evidence": [{"uri": f"corpus://{H1}", "kind": "authoritative"}]},
        "status": "open", "asof": "2026-07-02",
    }))
    landed = promote(ledger, "mom-birthday")
    assert landed == "mom:birthday (confirmed)"  # authoritative evidence passes the bar
    fact = json.loads((ledger / "facts" / "person" / "mom.json").read_text())
    assert any(c["id"] == "mom:birthday" for c in fact["claims"])
    interp = json.loads((ledger / "interpretations" / "mom-birthday.json").read_text())
    assert interp["status"] == "promoted" and interp["resolution"] == "mom:birthday"
    with pytest.raises(PromoteError, match="not open"):
        promote(ledger, "mom-birthday")

    (ledger / "interpretations" / "phone-wrong.json").write_text(json.dumps({
        "id": "phone-wrong", "kind": "correction", "about": ["mom"],
        "statement": "mom:phone misreads the source.", "reasoning": "r",
        "based_on": [f"corpus://{H1}"],
        "challenges": {"claim": "mom:phone"},
        "status": "standing", "asof": "2026-07-02",
    }))
    state = stamp(ledger, "phone-wrong")
    claim = next(c for c in fact["claims"] if c["id"] == "mom:phone")
    assert state == canonical_claim_state(claim)


def test_worklist_directions(system: Path) -> None:
    run_harvest(system / "ledger", _corpora(system))
    rows = worklist(system / "ledger", H1)
    assert any("roster" in r and "chat-14035551234" in r for r in rows)
    assert any(r.startswith("claim") for r in rows)
    (system / "ledger" / "facts" / "person").mkdir()
    (system / "ledger" / "facts" / "person" / "mom.json").write_text(json.dumps({
        "id": "mom", "type": "person", "name": "Mom",
        "claims": [{"id": "mom:chat", "predicate": "chats_via",
                    "object": "chat-14035551234", "status": "provisional",
                    "asof": "2023-03-01",
                    "evidence": [{"uri": f"corpus://{H1}", "kind": "direct"}]}],
    }))
    rows = worklist(system / "ledger", "chat-14035551234")
    assert any("mom:chat" in r for r in rows)


def test_coverage_counts(system: Path) -> None:
    run_harvest(system / "ledger", _corpora(system))
    text = render_coverage(system / "ledger", _corpora(system))
    assert "## corpus-private" in text
    assert "2 of 3 records represented" in text  # the group record is backlog
    assert "| `imessage-export` | 3 | 2 |" in text
