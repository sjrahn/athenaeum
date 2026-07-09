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


# ------------------------------ structured-value entity traversal (conv. 7)
# The roster shape `{"entity": <id>}` inside a claim `value` — an event's
# attendance, a group's members — is a traversal link like a claim object,
# in both directions, still within the type bound (spec/codex.md §3).


def _entity_scope(tmp_path: Path, facts: list[tuple[str, dict]], scope_yaml: str):
    """A minimal ledger + codex for exercising conv. 7 entity traversal."""
    ledger = tmp_path / "ledger"
    for type_, obj in facts:
        p = ledger / "facts" / type_ / f"{obj['id']}.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(obj))
    (ledger / "ledger.yaml").write_text("name: ledger\ncorpora: []\n")
    codex = tmp_path / "codices" / "codex-x"
    codex.mkdir(parents=True)
    (codex / "codex.yaml").write_text("name: codex-x\nscope:\n" + scope_yaml)
    return materialize(ledger, load_codex(codex))


def _person(pid: str) -> tuple[str, dict]:
    return ("person", {"id": pid, "type": "person", "name": pid.title()})


def _event_attendance(eid: str, value: object) -> tuple[str, dict]:
    return ("event", {"id": eid, "type": "event", "name": eid,
                      "claims": [{"id": f"{eid}:att", "predicate": "attendance",
                                  "value": value}]})


def test_scope_attendance_entity_pulls_person_outgoing(tmp_path: Path) -> None:
    """(i) outgoing: a scoped event's `attendance` entity pulls the person in."""
    scoped, _, problems = _entity_scope(
        tmp_path,
        [_event_attendance("fest", [{"entity": "steven", "role": "worked"}]),
         _person("steven")],
        "  roots: [fest]\n  traverse_types: [event, person]\n",
    )
    assert problems == []
    assert set(scoped) == {"fest", "steven"}


def test_scope_person_root_pulls_event_incoming(tmp_path: Path) -> None:
    """(ii) incoming: a person root pulls in an event whose attendance names them."""
    scoped, _, _ = _entity_scope(
        tmp_path,
        [_person("steven"),
         _event_attendance("fest", [{"entity": "steven", "role": "worked"}])],
        "  roots: [steven]\n  traverse_types: [person, event]\n",
    )
    assert set(scoped) == {"steven", "fest"}


def test_scope_entity_traversal_respects_bound(tmp_path: Path) -> None:
    """(iii) the type bound still blocks the entity hop — a person root does NOT
    pull an event whose type is outside `traverse_types`."""
    scoped, _, _ = _entity_scope(
        tmp_path,
        [_person("steven"),
         _event_attendance("fest", [{"entity": "steven", "role": "worked"}])],
        "  roots: [steven]\n  traverse_types: [person]\n",   # event unlisted
    )
    assert set(scoped) == {"steven"}


def test_scope_group_members_entity_traverses(tmp_path: Path) -> None:
    """(iv) the same roster shape on a group's `members` traverses; an
    unresolved-handle element (no `entity`) is simply not a link."""
    group = ("group", {"id": "crew", "type": "group", "name": "Crew",
                       "claims": [{"id": "crew:members", "predicate": "members",
                                   "value": [{"entity": "steven"},
                                             {"handle": "+15550001111",
                                              "name": "Mystery"}]}]})
    scoped, _, _ = _entity_scope(
        tmp_path, [group, _person("steven")],
        "  roots: [crew]\n  traverse_types: [group, person]\n",
    )
    assert set(scoped) == {"crew", "steven"}


def test_scope_entity_walk_tolerates_malformed(tmp_path: Path) -> None:
    """(v) malformed array elements never crash the walk; a well-formed
    `{"entity": …}` beside them still links, including one nested a dict deep."""
    messy = ["garbage", 42, None, {"role": "worked"},
             {"entity": "steven"}, {"outer": {"entity": "greg"}}]
    scoped, _, problems = _entity_scope(
        tmp_path,
        [_event_attendance("fest", messy), _person("steven"), _person("greg")],
        "  roots: [fest]\n  traverse_types: [event, person]\n",
    )
    assert problems == []
    assert set(scoped) == {"fest", "steven", "greg"}


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


def test_build_refuses_incomplete_join(system: Path) -> None:
    """A missing registered corpus makes every hash it holds unresolvable —
    sensitivity is underivable, so the wall fails closed (spec/codex.md §6)."""
    import shutil

    from ath._cli import main as ath_main
    from codex.build import BuildError

    manifest = load_codex(system / "codices" / "codex-demo")
    shutil.rmtree(system / "corpora" / "corpus-private")
    join = _join(system)
    assert not join.complete
    with pytest.raises(BuildError, match="incomplete"):
        build(manifest, system / "ledger", join, profile="public",
              today="2026-07-03")
    with pytest.raises(BuildError, match="incomplete"):
        build(manifest, system / "ledger", join, profile="private",
              today="2026-07-03")
    # the CLI's vault surfaces refuse too
    assert ath_main(["codex", "codex-demo", "notes", "--root", str(system)]) == 2
    assert ath_main(["codex", "codex-demo", "check", "--root", str(system)]) == 2


def test_unresolvable_evidence_fails_closed(system: Path) -> None:
    """Evidence citing a hash that resolves in no corpus is private-backed."""
    dangling = "c" * 64
    p = system / "ledger" / "facts" / "album" / "obscura.json"
    o = json.loads(p.read_text())
    o["claims"][0]["evidence"] = [{"uri": f"corpus://{dangling}", "kind": "direct"}]
    p.write_text(json.dumps(o))
    manifest = load_codex(system / "codices" / "codex-demo")
    scoped, riding, _ = materialize(system / "ledger", manifest)
    vault = generate(scoped, riding, _join(system), profile="public",
                     today="2026-07-03")
    assert "album/obscura.md" not in vault  # sole claim fails closed → fully private


def test_public_build_rasters_without_false_leak(system: Path) -> None:
    """A rastered asset's filename must never trip the leak check: assets are
    named by a 32-hex urihash prefix, deliberately shorter than a corpus hash,
    so a public build whose visual evidence is public-backed is clean."""
    import frontmatter

    from corpus import hashing, paths, records
    from corpus.store import LocalArtifactStore

    # stage a real public image record so the raster path genuinely runs
    src = Path(__file__).parent / "data" / "sample.png"
    h_img = hashing.hash_file(src)["blake3"]
    pub_root = system / "corpora" / "corpus"
    LocalArtifactStore(pub_root).put(h_img, "png", src)
    post = frontmatter.Post("")
    post.metadata.update({"id": h_img, "title": "Public image",
                          "status": "normalized",
                          "touch": ["corpus.compile@0.1.0"]})
    records.set_artifact_block(post, mime="image/png",
                               fields={"title": "sample.png"})
    records.dump(post, paths.record_path(pub_root, h_img))

    p = system / "ledger" / "facts" / "album" / "obscura.json"
    o = json.loads(p.read_text())
    o["claims"][0]["evidence"] = [
        {"uri": f"corpus://{h_img}?bbox=0.0,0.0,0.5,0.5", "kind": "direct"}]
    p.write_text(json.dumps(o))

    manifest = load_codex(system / "codices" / "codex-demo")
    res = build(manifest, system / "ledger", _join(system), profile="public",
                today="2026-07-08")
    assert res.rastered == 1
    assert res.ok, res.problems
    note = (manifest.root / "build" / "public" / "content" / "album" /
            "obscura.md").read_text()
    assert "](assets/" in note


def test_interp_claim_id_basis_inherits_privacy(system: Path) -> None:
    """based_on may cite claim ids (§7.2): the interpretation inherits the
    claim's privacy; an unresolvable basis fails closed."""
    interps = system / "ledger" / "interpretations"
    (interps / "tour-guess.json").write_text(json.dumps({
        "id": "tour-guess", "kind": "hypothesis", "about": ["gorguts"],
        "statement": "The 2019 show was the Colored Sands tour.",
        "confidence": "plausible", "reasoning": "r",
        "based_on": ["gorguts:seen-live"],  # a private-backed claim
        "status": "open", "asof": "2026-01-01",
    }))
    (interps / "ghost-basis.json").write_text(json.dumps({
        "id": "ghost-basis", "kind": "hypothesis", "about": ["gorguts"],
        "statement": "GHOSTBASIS statement.",
        "confidence": "plausible", "reasoning": "r",
        "based_on": ["no-such-fact:no-such-claim"],
        "status": "open", "asof": "2026-01-01",
    }))
    manifest = load_codex(system / "codices" / "codex-demo")
    scoped, riding, _ = materialize(system / "ledger", manifest)
    join = _join(system)
    priv = generate(scoped, riding, join, profile="private", today="2026-07-03")
    assert "Colored Sands" in priv["band/gorguts.md"]
    assert "GHOSTBASIS" in priv["band/gorguts.md"]
    pub = generate(scoped, riding, join, profile="public", today="2026-07-03")
    assert "Colored Sands" not in pub["band/gorguts.md"]
    assert "GHOSTBASIS" not in pub["band/gorguts.md"]
