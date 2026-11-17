"""An evidence `anchor` (or `quote`) that is not a string is a schema error, never "no
anchor": generator scratch objects left in the slot used to pass check and verify with 0
errors, so the entry silently read as a record-level cite it never was."""

from __future__ import annotations

import json

from ledger._cli import main as ledger_main
from tests.test_verify_text_plain import _TABLE, _verify


def test_check_rejects_an_object_anchor(tmp_path, capsys):
    (tmp_path / "athenaeum.yaml").write_text("visibility: public\n")
    (tmp_path / "corpus" / "records").mkdir(parents=True)
    facts = tmp_path / "ledger" / "facts" / "part"
    facts.mkdir(parents=True)
    (tmp_path / "ledger" / "interpretations").mkdir()
    (facts / "bcm.json").write_text(json.dumps({
        "id": "bcm", "type": "part", "name": "BCM",
        "sources": {"s1": {"record": "a" * 64}},
        "claims": [{"id": "bcm:mass", "predicate": "mass", "value": "1 kg",
                    "status": "provisional", "asof": "2026-11-17",
                    "evidence": [{"source": "s1", "kind": "direct", "quote": ["1 kg"],
                                  "anchor": {"rows": [{"page": 10, "line": "1 kg"}]}}]}],
    }))
    assert ledger_main(["check", "--root", str(tmp_path)]) != 0
    out = capsys.readouterr().out
    assert "evidence `anchor` must be a string, not dict" in out
    assert "evidence `quote` must be a string, not list" in out


def test_verify_never_reads_an_object_anchor_as_record_level(tmp_path):
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    _res, root, _rid = _verify(tmp_path, _TABLE.encode(), "Bohr radius")
    f = root.parent / "ledger" / "facts" / "quantity" / "c.json"
    fact = json.loads(f.read_text())
    fact["claims"][0]["evidence"][0]["anchor"] = {"rows": [{"line": "Bohr radius"}]}
    f.write_text(json.dumps(fact))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(root.parent / "ledger", join, {}, stamp=False, today="2026-11-17")
    assert res.verified == 0 and any("anchor is a dict" in e for e in res.errors)
