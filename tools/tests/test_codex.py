"""The codex layer: scope materialization, note generation with profiles,
the build's leak check and certificate (spec/codex.md)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from codex.build import build
from codex.manifest import load_codex
from codex.notes import generate
from codex.scope import materialize
from ledger.corpora import CorpusJoin, RegisteredCorpus

H_PUB = "a" * 64
H_PRIV = "b" * 64


def _record(root: Path, h: str, title: str) -> None:
    p = root / "records" / h[:2] / f"{h}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nid: {h}\ntitle: {title}\nstatus: normalized\n"
        "touch:\n- corpus.compile@0.1.0\n---\n\n"
        "<!--segment text\naddress: el=1\n-->\nbody text\n<!--/segment-->\n",
        encoding="utf-8",
    )


@pytest.fixture()
def system(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "athenaeum.yaml").write_text(
        "org: https://example.test/x\n"
        "corpora:\n  corpus:\n    visibility: public\n"
        "  corpus-private:\n    visibility: private\n"
        "ledger:\n  ledger:\n"
        "codices:\n  codex-demo:\n"
    )
    _record(root / "corpora" / "corpus", H_PUB, "Public source")
    _record(root / "corpora" / "corpus-private", H_PRIV, "Private source")
    ledger = root / "ledger"
    (ledger / "interpretations").mkdir(parents=True)
    (ledger / "ledger.yaml").write_text("name: ledger\ncorpora: [corpus, corpus-private]\n")

    def fact(type_, obj):
        p = ledger / "facts" / type_ / f"{obj['id']}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj))

    fact("band", {
        "id": "gorguts", "type": "band", "name": "Gorguts",
        "claims": [
            {"id": "gorguts:formed", "predicate": "formed", "value": "1989",
             "status": "confirmed", "asof": "2026-01-01",
             "evidence": [{"uri": f"corpus://{H_PUB}?el=1", "quote": "body text",
                           "kind": "authoritative"}]},
            {"id": "gorguts:seen-live", "predicate": "seen_live", "value": "2019 tour",
             "status": "provisional", "asof": "2026-01-01",
             "evidence": [{"uri": f"corpus://{H_PRIV}", "kind": "direct"}]},
        ],
    })
    fact("album", {
        "id": "obscura", "type": "album", "name": "Obscura",
        "claims": [{"id": "obscura:by", "predicate": "released_by", "object": "gorguts",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"uri": f"corpus://{H_PUB}", "kind": "authoritative"}]}],
    })
    fact("ticket", {  # fully private-backed concept
        "id": "gorguts-stub", "type": "ticket", "name": "Ticket stub",
        "claims": [{"id": "gorguts-stub:show", "predicate": "admits_to",
                    "object": "gorguts", "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"uri": f"corpus://{H_PRIV}", "kind": "direct"}]}],
    })
    fact("person", {"id": "luc-lemay", "type": "person", "name": "Luc Lemay",
                    "claims": [{"id": "luc-lemay:in", "predicate": "member_of",
                                "object": "gorguts", "status": "confirmed",
                                "asof": "2026-01-01",
                                "evidence": [{"uri": f"corpus://{H_PUB}",
                                              "kind": "authoritative"}]}]})
    (ledger / "interpretations" / "second-guitarist.json").write_text(json.dumps({
        "id": "second-guitarist", "kind": "hypothesis", "about": ["gorguts"],
        "statement": "The 1998 lineup had a second guitarist.",
        "confidence": "plausible", "reasoning": "r",
        "based_on": [f"corpus://{H_PUB}"], "status": "open", "asof": "2026-01-01",
    }))

    codex = root / "codices" / "codex-demo"
    codex.mkdir(parents=True)
    (codex / "codex.yaml").write_text(
        "name: codex-demo\ndisplay_name: Demo\ndescription: a test codex\n"
        "scope:\n  types: [band, album]\n"
        "  roots: [gorguts]\n"
        "  traverse_types: [band, album, ticket]\n"
        "profiles:\n  public:\n    redact: exclude\n"
    )
    return root


def _join(root: Path) -> CorpusJoin:
    return CorpusJoin([
        RegisteredCorpus("corpus", root / "corpora" / "corpus", private=False),
        RegisteredCorpus("corpus-private", root / "corpora" / "corpus-private",
                         private=True),
    ])


def test_scope_traversal_is_bounded(system: Path) -> None:
    manifest = load_codex(system / "codices" / "codex-demo")
    scoped, riding, problems = materialize(system / "ledger", manifest)
    # types pull band+album; incoming traversal pulls the ticket (targets
    # gorguts, admissible type); the person is NOT traversable (not in bound)
    assert set(scoped) == {"gorguts", "obscura", "gorguts-stub"}
    assert set(riding) == {"second-guitarist"}
    assert problems == []


def test_notes_profiles(system: Path) -> None:
    manifest = load_codex(system / "codices" / "codex-demo")
    scoped, riding, _ = materialize(system / "ledger", manifest)
    join = _join(system)
    private_vault = generate(scoped, riding, join, profile="private", today="2026-07-03")
    assert set(private_vault) == {"band/gorguts.md", "album/obscura.md",
                                  "ticket/gorguts-stub.md"}
    note = private_vault["band/gorguts.md"]
    assert "concept: gorguts" in note and "generated_from:" in note
    assert "`confirmed`" in note and "`provisional`" in note  # the ladder survives
    assert "second guitarist" in note  # interpretive, marked
    assert "> [!warning]" in note
    assert f"corpus://{H_PRIV}" in note  # private profile renders everything

    public_vault = generate(scoped, riding, join, profile="public",
                            redact="exclude", today="2026-07-03")
    assert "ticket/gorguts-stub.md" not in public_vault  # fully private → omitted
    pub_note = public_vault["band/gorguts.md"]
    assert H_PRIV not in pub_note  # private-backed claim excluded
    assert "seen_live" not in pub_note
    assert "formed" in pub_note

    stub_vault = generate(scoped, riding, join, profile="public",
                          redact="stub", today="2026-07-03")
    assert "*(private evidence)*" in stub_vault["band/gorguts.md"]


def test_build_resolves_and_certifies(system: Path) -> None:
    manifest = load_codex(system / "codices" / "codex-demo")
    join = _join(system)
    res = build(manifest, system / "ledger", join, profile="public",
                today="2026-07-03")
    assert res.ok, res.problems
    content = manifest.root / "build" / "public" / "content"
    note = (content / "band" / "gorguts.md").read_text()
    assert "Public source —" in note  # human citation resolved
    assert (content / "index.md").is_file()
    cert = json.loads(res.certificate.read_text())
    assert cert["profile"] == "public"
    assert cert["corpus_touches"] == {H_PUB: "corpus.compile@0.1.0"}
    assert cert["ledger_commit"] == "unversioned"


def test_leak_check_catches_a_planted_leak(system: Path) -> None:
    manifest = load_codex(system / "codices" / "codex-demo")
    # plant a private hash inside a public claim's value (evidence stays public)
    p = system / "ledger" / "facts" / "album" / "obscura.json"
    o = json.loads(p.read_text())
    o["claims"][0]["value"] = f"see corpus://{H_PRIV}"
    p.write_text(json.dumps(o))
    res = build(manifest, system / "ledger", _join(system), profile="public",
                today="2026-07-03")
    assert not res.ok
    assert any("LEAK" in x and H_PRIV[:12] in x for x in res.problems)


def test_ath_codex_dispatch(system: Path, capsys: pytest.CaptureFixture[str]) -> None:
    from ath._cli import main as ath_main

    assert ath_main(["codex", "codex-demo", "scope", "--root", str(system)]) == 0
    out = capsys.readouterr().out
    assert "3 facts, 1 riding interpretations" in out
    assert ath_main(["codex", "codex-demo", "notes", "--root", str(system)]) == 0
    assert (system / "codices" / "codex-demo" / "notes" / "band" / "gorguts.md").is_file()
    assert ath_main(["codex", "codex-demo", "build", "--root", str(system),
                     "--profile", "public"]) == 0
