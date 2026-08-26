"""The `cco-release` spine format adapter (spec/ledger.md §15.2): resolution
against a tiny synthetic CCO-release-shaped archive — a zip carrying
`.../src/cco-iris/{date}/CommonCoreOntologiesMerged.ttl`, mimicking ROBOT's
actual block-comment output shape (the real release ships no OWL/RDF-XML for
this file; see `refdata/adapters/cco_release.py`'s module docstring for why
this adapter scans that shape directly rather than depending on `rdflib`).
No optional dependency, so no importorskip guard needed.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from refdata.adapters import adapter_available, cco_release
from refdata.errors import EntryNotFound

_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .
@prefix xsd: <http://www.w3.org/2001/XMLSchema#> .

###  https://www.commoncoreontologies.org/ont00001017
<https://www.commoncoreontologies.org/ont00001017> rdf:type owl:Class ;
  rdfs:subClassOf <http://purl.obolibrary.org/obo/BFO_0000004> ;
  rdfs:label "Agent"@en ;
  <http://www.w3.org/2004/02/skos/core#definition>
    "A Material Entity that bears an Agent Capability."@en .


###  https://www.commoncoreontologies.org/ont00000042
<https://www.commoncoreontologies.org/ont00000042> rdf:type owl:Class ;
  rdfs:label "Agent"@en ;
  <http://www.w3.org/2004/02/skos/core#definition>
    "A duplicate-label decoy for ambiguity testing."@en .


###  https://www.commoncoreontologies.org/ont00001765
<https://www.commoncoreontologies.org/ont00001765> rdf:type owl:DatatypeProperty ;
  rdfs:label "has text value"@en ;
  owl:deprecated "true"^^xsd:boolean ;
  <http://www.w3.org/2004/02/skos/core#definition>
    "Deprecated without direct replacement."@en .


###  https://www.commoncoreontologies.org/ont00001760
<https://www.commoncoreontologies.org/ont00001760> rdf:type owl:AnnotationProperty .


###  http://purl.obolibrary.org/obo/BFO_0000040
<http://purl.obolibrary.org/obo/BFO_0000040> rdf:type owl:Class ;
                                             rdfs:label "material entity"@en .
"""


def _build_zip(
    path: Path, *, repo_prefix: str = "CommonCoreOntology-CommonCoreOntologies-d846c40",
    date: str = "2026-08-13",
) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{repo_prefix}/src/cco-iris/{date}/CommonCoreOntologiesMerged.ttl", _TTL)


def _handle(tmp_path: Path, **kwargs):
    p = tmp_path / "cco.zip"
    _build_zip(p, **kwargs)
    return cco_release.open_archive(p)


def test_adapter_registered_and_available() -> None:
    assert adapter_available("cco-release") is True


def test_resolve_by_native_id(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    result = cco_release.resolve_entry(handle, "ont00001017")
    assert result.canonical_id == "ont00001017"
    assert result.title == "Agent"
    assert "Agent" in result.text
    assert "Material Entity" in result.text


def test_entry_not_found(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    try:
        cco_release.resolve_entry(handle, "ont-does-not-exist")
    except EntryNotFound:
        pass
    else:
        raise AssertionError("expected EntryNotFound")


def test_bfo_namespaced_terms_excluded_from_cco_enumeration(tmp_path: Path) -> None:
    """The merged file bundles BFO's own terms too (it's a stand-alone
    release) — this adapter deliberately excludes anything outside the CCO
    namespace, so `bfo:`'s own dataset owns that resolution instead."""
    handle = _handle(tmp_path)
    terms = {t.native_id for t in cco_release.iter_terms(handle)}
    assert "BFO_0000040" not in terms
    try:
        cco_release.resolve_entry(handle, "BFO_0000040")
    except EntryNotFound:
        pass
    else:
        raise AssertionError("expected EntryNotFound for a BFO-namespaced id")


def test_iter_terms_includes_datatype_property_and_deprecated_flag(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    terms = {t.native_id: t for t in cco_release.iter_terms(handle)}
    assert terms["ont00001765"].label == "has text value"
    assert terms["ont00001765"].deprecated is True
    assert terms["ont00001017"].deprecated is False


def test_annotation_property_with_no_label_excluded_from_terms(tmp_path: Path) -> None:
    """`ont00001760` is an `owl:AnnotationProperty` — not one of the
    resolvable term types this adapter enumerates (Class/ObjectProperty/
    DatatypeProperty/NamedIndividual)."""
    handle = _handle(tmp_path)
    terms = {t.native_id for t in cco_release.iter_terms(handle)}
    assert "ont00001760" not in terms


def test_duplicate_labels_both_enumerated(tmp_path: Path) -> None:
    """Two distinct CCO terms share the label 'Agent' in this fixture — the
    adapter itself doesn't resolve by label (that's `refdata.spine`'s job,
    which is where ambiguity becomes an error); it just enumerates both."""
    handle = _handle(tmp_path)
    agent_ids = {t.native_id for t in cco_release.iter_terms(handle) if t.label == "Agent"}
    assert agent_ids == {"ont00001017", "ont00000042"}


def test_search_entries_label_and_definition(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    suggest_hits = cco_release.search_entries(handle, "Agent", 10, mode="suggest")
    assert {h.native_id for h in suggest_hits} == {"ont00001017", "ont00000042"}

    fulltext_hits = cco_release.search_entries(handle, "Capability", 10, mode="fulltext")
    assert [h.native_id for h in fulltext_hits] == ["ont00001017"]


def test_search_invalid_mode_raises(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    try:
        cco_release.search_entries(handle, "Agent", 10, mode="bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_member_located_by_suffix_regardless_of_variable_directories(tmp_path: Path) -> None:
    """Both the repo commit-hash prefix and the date subdirectory vary per
    real release — the member is found by suffix pattern, not a hardcoded
    path."""
    handle = _handle(
        tmp_path, repo_prefix="CommonCoreOntology-CommonCoreOntologies-ffff000", date="2020-01-01"
    )
    result = cco_release.resolve_entry(handle, "ont00001017")
    assert result.title == "Agent"
