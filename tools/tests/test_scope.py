"""Scope selection and traversal (`spec/ledger.md` §12.1).

Builds small temp ledger trees (`facts/{type}/{slug}.json` + optional
`facts/LINEAGE.json`) — no corpus/instance needed, since `evidence:
references` only reads a fact's own `sources` table (§6.2).
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger.scope import evaluate_scope

H = "a" * 64


def _write(root: Path, ftype: str, fid: str, **extra: object) -> None:
    d = root / "facts" / ftype
    d.mkdir(parents=True, exist_ok=True)
    obj = {"id": fid, "type": ftype, "name": extra.pop("name", fid.title()), **extra}
    (d / f"{fid}.json").write_text(json.dumps(obj), encoding="utf-8")


def _lineage(root: Path, rows: dict[str, str]) -> None:
    (root / "facts").mkdir(parents=True, exist_ok=True)
    (root / "facts" / "LINEAGE.json").write_text(json.dumps(rows), encoding="utf-8")


def _members(result: dict) -> set[str]:
    return {m["id"] for m in result["members"]}


def _depth(result: dict) -> dict[str, int]:
    return {m["id"]: m["depth"] for m in result["members"]}


# ------------------------------------------------------------------ seeds


def test_id_seed_resolves_through_lineage(tmp_path: Path) -> None:
    """A retired id seeds its survivor; the retired id never appears (§4.1)."""
    _write(tmp_path, "person", "bob")
    _lineage(tmp_path, {"old-bob": "bob"})
    result = evaluate_scope(tmp_path, {"seed": {"ids": ["old-bob"]}, "follow": []})
    assert _members(result) == {"bob"}
    assert result["unknown_seeds"] == []


def test_unknown_seed_reported_not_fatal(tmp_path: Path) -> None:
    _write(tmp_path, "person", "bob")
    result = evaluate_scope(tmp_path, {"seed": {"ids": ["bob", "nope"]}, "follow": []})
    assert _members(result) == {"bob"}
    assert result["unknown_seeds"] == ["nope"]


def test_type_seed_selects_every_fact_of_type(tmp_path: Path) -> None:
    _write(tmp_path, "person", "alice")
    _write(tmp_path, "person", "bob")
    _write(tmp_path, "band", "gorguts")
    result = evaluate_scope(tmp_path, {"seed": {"type": "person"}, "follow": []})
    assert _members(result) == {"alice", "bob"}


# ------------------------------------------------------------------ match seed operator grammar


@pytest.fixture()
def songs(tmp_path: Path) -> Path:
    _write(tmp_path, "song", "song-a", name="Nostalgia",
           claims=[{"id": "song-a:genre", "predicate": "genre", "value": "death-metal"},
                   {"id": "song-a:length", "predicate": "length", "value": "5:20"}])
    _write(tmp_path, "song", "song-b", name="Obscura",
           claims=[{"id": "song-b:genre", "predicate": "genre", "value": "black-metal"}])
    _write(tmp_path, "song", "song-c", name="Colored Sands",
           claims=[{"id": "song-c:genre", "predicate": "genre", "value": "death-metal"}])
    return tmp_path


def test_match_equals(songs: Path) -> None:
    result = evaluate_scope(songs, {
        "seed": {"match": {"claim.genre": {"equals": "death-metal"}}}, "follow": []})
    assert _members(result) == {"song-a", "song-c"}


def test_match_in(songs: Path) -> None:
    result = evaluate_scope(songs, {
        "seed": {"match": {"claim.genre": {"in": ["death-metal", "black-metal"]}}},
        "follow": []})
    assert _members(result) == {"song-a", "song-b", "song-c"}


def test_match_glob(songs: Path) -> None:
    result = evaluate_scope(songs, {
        "seed": {"match": {"name": {"glob": "Nostalg*"}}}, "follow": []})
    assert _members(result) == {"song-a"}


def test_match_matches_regex(songs: Path) -> None:
    result = evaluate_scope(songs, {
        "seed": {"match": {"name": {"matches": "^Obscura$"}}}, "follow": []})
    assert _members(result) == {"song-b"}


def test_match_exists(songs: Path) -> None:
    present = evaluate_scope(songs, {
        "seed": {"match": {"claim.length": {"exists": True}}}, "follow": []})
    assert _members(present) == {"song-a"}
    absent = evaluate_scope(songs, {
        "seed": {"match": {"claim.length": {"exists": False}}}, "follow": []})
    assert _members(absent) == {"song-b", "song-c"}


def test_match_all_of(songs: Path) -> None:
    result = evaluate_scope(songs, {
        "seed": {"match": {"all_of": [
            {"claim.genre": {"equals": "death-metal"}},
            {"name": {"glob": "Colored*"}},
        ]}}, "follow": []})
    assert _members(result) == {"song-c"}


def test_match_any_of(songs: Path) -> None:
    result = evaluate_scope(songs, {
        "seed": {"match": {"any_of": [
            {"name": {"matches": "^Obscura$"}},
            {"name": {"glob": "Colored*"}},
        ]}}, "follow": []})
    assert _members(result) == {"song-b", "song-c"}


def test_match_none_of(songs: Path) -> None:
    result = evaluate_scope(songs, {
        "seed": {"match": {"none_of": [{"claim.genre": {"equals": "black-metal"}}]}},
        "follow": []})
    assert _members(result) == {"song-a", "song-c"}


def test_match_missing_field_is_false(songs: Path) -> None:
    """missing-is-false (§10): a predicate no claim carries never matches, exists() aside."""
    result = evaluate_scope(songs, {
        "seed": {"match": {"claim.tempo": {"equals": "180"}}}, "follow": []})
    assert _members(result) == set()


# ------------------------------------------------------------------ traversal kinds


def test_entity_ref_traversal_into_nested_array_values(tmp_path: Path) -> None:
    _write(tmp_path, "band", "gorguts", claims=[
        {"id": "gorguts:lineup", "predicate": "lineup",
         "value": [{"entity": "luc-lemay", "role": "vocals"}]},
    ])
    _write(tmp_path, "person", "luc-lemay")
    result = evaluate_scope(tmp_path, {"seed": {"ids": ["gorguts"]}, "follow": ["entity"]})
    assert _members(result) == {"gorguts", "luc-lemay"}
    assert _depth(result)["luc-lemay"] == 1


def test_wikilink_traversal(tmp_path: Path) -> None:
    _write(tmp_path, "person", "luc-lemay", claims=[
        {"id": "luc-lemay:residence", "predicate": "residence", "value": "Lives in [[quebec]]"},
    ])
    _write(tmp_path, "place", "quebec")
    result = evaluate_scope(tmp_path, {"seed": {"ids": ["luc-lemay"]}, "follow": ["wikilink"]})
    assert _members(result) == {"luc-lemay", "quebec"}


def test_object_traversal(tmp_path: Path) -> None:
    _write(tmp_path, "person", "alice", claims=[
        {"id": "alice:employer", "predicate": "employer", "object": "acme"},
    ])
    _write(tmp_path, "org", "acme")
    result = evaluate_scope(tmp_path, {"seed": {"ids": ["alice"]}, "follow": ["object"]})
    assert _members(result) == {"alice", "acme"}


def test_edge_participation_both_directions(tmp_path: Path) -> None:
    """A concept in scope pulls in a touching edge; the edge pulls in the
    other participants (§12.1)."""
    _write(tmp_path, "band", "gorguts")
    _write(tmp_path, "person", "alice")
    _write(tmp_path, "event", "concert-2026", participants=["gorguts", "alice"], title="Show")

    from_concept = evaluate_scope(
        tmp_path, {"seed": {"ids": ["gorguts"]}, "follow": ["participants"]})
    assert _members(from_concept) == {"gorguts", "alice", "concert-2026"}

    from_edge = evaluate_scope(
        tmp_path, {"seed": {"ids": ["concert-2026"]}, "follow": ["participants"], "depth": 1})
    assert _members(from_edge) == {"gorguts", "alice", "concert-2026"}


def test_edge_subject_also_joins(tmp_path: Path) -> None:
    _write(tmp_path, "person", "alice")
    _write(tmp_path, "review", "alice-review", subject="alice", title="Review")
    result = evaluate_scope(tmp_path, {"seed": {"ids": ["alice"]}, "follow": ["participants"]})
    assert _members(result) == {"alice", "alice-review"}


def test_roster_does_not_add_facts_but_is_carried_in_result(tmp_path: Path) -> None:
    _write(tmp_path, "band", "gorguts",
           artifacts=[{"uri": f"corpus://{H}", "role": "documents"}])
    result = evaluate_scope(
        tmp_path, {"seed": {"ids": ["gorguts"]}, "follow": ["roster"]})
    assert _members(result) == {"gorguts"}  # roster never adds facts
    assert result["roster"] == {"gorguts": [f"corpus://{H}"]}


def test_default_follow_excludes_roster(tmp_path: Path) -> None:
    _write(tmp_path, "band", "gorguts",
           artifacts=[{"uri": f"corpus://{H}", "role": "documents"}])
    result = evaluate_scope(tmp_path, {"seed": {"ids": ["gorguts"]}})
    assert "roster" not in result


# ------------------------------------------------------------------ depth + cycles + determinism


def test_depth_limiting(tmp_path: Path) -> None:
    _write(tmp_path, "node", "n1", claims=[{"id": "n1:next", "predicate": "next", "object": "n2"}])
    _write(tmp_path, "node", "n2", claims=[{"id": "n2:next", "predicate": "next", "object": "n3"}])
    _write(tmp_path, "node", "n3", claims=[{"id": "n3:next", "predicate": "next", "object": "n4"}])
    _write(tmp_path, "node", "n4")

    seeds_only = evaluate_scope(
        tmp_path, {"seed": {"ids": ["n1"]}, "follow": ["object"], "depth": 0})
    assert _members(seeds_only) == {"n1"}

    one_hop = evaluate_scope(
        tmp_path, {"seed": {"ids": ["n1"]}, "follow": ["object"], "depth": 1})
    assert _members(one_hop) == {"n1", "n2"}
    assert _depth(one_hop) == {"n1": 0, "n2": 1}

    unlimited = evaluate_scope(
        tmp_path, {"seed": {"ids": ["n1"]}, "follow": ["object"]})
    assert _members(unlimited) == {"n1", "n2", "n3", "n4"}
    assert _depth(unlimited)["n4"] == 3


def test_cycle_safety(tmp_path: Path) -> None:
    """A -> B -> A terminates (visited-set closure)."""
    _write(tmp_path, "person", "alice",
           claims=[{"id": "alice:knows", "predicate": "knows", "object": "bob"}])
    _write(tmp_path, "person", "bob",
           claims=[{"id": "bob:knows", "predicate": "knows", "object": "alice"}])
    result = evaluate_scope(tmp_path, {"seed": {"ids": ["alice"]}, "follow": ["object"]})
    assert _members(result) == {"alice", "bob"}
    assert _depth(result) == {"alice": 0, "bob": 1}


def test_determinism(tmp_path: Path) -> None:
    _write(tmp_path, "band", "gorguts", claims=[
        {"id": "gorguts:lineup", "predicate": "lineup",
         "value": [{"entity": "luc-lemay", "role": "vocals"},
                   {"entity": "steeve-hurdle", "role": "guitar"}]},
    ])
    _write(tmp_path, "person", "luc-lemay", claims=[
        {"id": "luc-lemay:residence", "predicate": "residence", "value": "Lives in [[quebec]]"}])
    _write(tmp_path, "person", "steeve-hurdle")
    _write(tmp_path, "place", "quebec")
    spec = {"seed": {"ids": ["gorguts"]}, "follow": ["entity", "wikilink"]}
    first = evaluate_scope(tmp_path, spec)
    second = evaluate_scope(tmp_path, spec)
    assert first == second


# ------------------------------------------------------------------ evidence


def test_evidence_references_carries_derived_uris(tmp_path: Path) -> None:
    d = tmp_path / "facts" / "person"
    d.mkdir(parents=True)
    obj = {
        "id": "evidenced", "type": "person", "name": "E",
        "sources": {"s1": {"record": H}, "s2": {"ref": "wikipedia/Evidenced"}},
        "claims": [
            {"id": "evidenced:note", "predicate": "note", "value": "x",
             "evidence": [{"source": "s1", "anchor": "p3"}, {"source": "s2"}]},
        ],
    }
    (d / "evidenced.json").write_text(json.dumps(obj), encoding="utf-8")

    result = evaluate_scope(
        tmp_path, {"seed": {"ids": ["evidenced"]}, "follow": [], "evidence": "references"})
    assert result["evidence"]["evidenced"] == sorted([f"corpus://{H}?p3",
                                                        "ref://wikipedia/Evidenced"])


def test_evidence_none_omits_evidence_key(tmp_path: Path) -> None:
    _write(tmp_path, "person", "bob")
    result = evaluate_scope(tmp_path, {"seed": {"ids": ["bob"]}, "follow": []})
    assert "evidence" not in result


def test_evidence_resolved_not_implemented(tmp_path: Path) -> None:
    _write(tmp_path, "person", "bob")
    with pytest.raises(NotImplementedError):
        evaluate_scope(tmp_path, {"seed": {"ids": ["bob"]}, "evidence": "resolved"})


# ------------------------------------------------------------------ malformed spec


def test_malformed_spec_not_a_dict(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, [])  # type: ignore[arg-type]


def test_malformed_spec_missing_seed(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, {})


def test_malformed_spec_seed_needs_exactly_one_key(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, {"seed": {}})
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, {"seed": {"ids": ["a"], "type": "person"}})


def test_malformed_spec_ids_not_list_of_strings(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, {"seed": {"ids": "bob"}})
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, {"seed": {"ids": [1, 2]}})


def test_malformed_spec_bad_follow_kind(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, {"seed": {"type": "person"}, "follow": ["nonsense"]})


def test_malformed_spec_bad_depth(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, {"seed": {"type": "person"}, "depth": -1})
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, {"seed": {"type": "person"}, "depth": True})
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, {"seed": {"type": "person"}, "depth": "1"})


def test_malformed_spec_bad_evidence(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        evaluate_scope(tmp_path, {"seed": {"type": "person"}, "evidence": "bogus"})
