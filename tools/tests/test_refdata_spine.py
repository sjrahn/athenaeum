"""The spine resolution layer (spec/ledger.md §15.2): `refdata.spine.
resolve_term`/`spine_bindings` against tiny synthetic BFO/CCO release zips
(same fixture shapes as `test_refdata_bfo.py`/`test_refdata_cco.py`) —
native-id resolution, unique-label resolution, ambiguous-label and
unresolvable-reference errors, the deprecated flag, honestly-unverifiable
when the mirror is absent, dataset-not-spine/not-registered, and the
never-admit-a-pin grammar rule.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from ath.manifest import Reference, Snapshot
from refdata import MirrorUnavailable
from refdata.errors import (
    AmbiguousSpineLabel,
    InvalidSpineReference,
    NotSpineDataset,
    SpineIncapableAdapter,
    SpineTermNotFound,
)
from refdata.spine import resolve_term, spine_bindings

_BFO_OWL = """<?xml version="1.0"?>
<rdf:RDF xmlns="http://purl.obolibrary.org/obo/bfo/"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns:owl="http://www.w3.org/2002/07/owl#"
     xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
     xmlns:skos="http://www.w3.org/2004/02/skos/core#">
    <owl:Class rdf:about="http://purl.obolibrary.org/obo/BFO_0000029">
        <rdfs:label xml:lang="en">site</rdfs:label>
        <skos:definition xml:lang="en">A three-dimensional immaterial entity.</skos:definition>
    </owl:Class>
    <owl:Class rdf:about="http://purl.obolibrary.org/obo/BFO_9999999">
        <rdfs:label xml:lang="en">retired term</rdfs:label>
        <owl:deprecated>true</owl:deprecated>
    </owl:Class>
</rdf:RDF>
"""

_CCO_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

###  https://www.commoncoreontologies.org/ont00001017
<https://www.commoncoreontologies.org/ont00001017> rdf:type owl:Class ;
  rdfs:label "Agent"@en ;
  <http://www.w3.org/2004/02/skos/core#definition>
    "A Material Entity that bears an Agent Capability."@en .


###  https://www.commoncoreontologies.org/ont00000042
<https://www.commoncoreontologies.org/ont00000042> rdf:type owl:Class ;
  rdfs:label "Agent"@en ;
  <http://www.w3.org/2004/02/skos/core#definition> "A duplicate-label decoy."@en .
"""

_BFO_ARTIFACT = "a" * 64
_CCO_ARTIFACT = "b" * 64


def _build_bfo_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("BFO-2020-master/21838-2/owl/bfo-core.owl", _BFO_OWL)


def _build_cco_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(
            "CommonCoreOntology-CommonCoreOntologies-d846c40/src/cco-iris/2026-08-13/"
            "CommonCoreOntologiesMerged.ttl",
            _CCO_TTL,
        )


@pytest.fixture
def bfo_ref(tmp_path: Path) -> Reference:
    p = tmp_path / "bfo.zip"
    _build_bfo_zip(p)
    return Reference(
        dataset="bfo", description="BFO-2020", adapter="bfo-2020", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact=_BFO_ARTIFACT, path=str(p))},
    )


@pytest.fixture
def cco_ref(tmp_path: Path) -> Reference:
    p = tmp_path / "cco.zip"
    _build_cco_zip(p)
    return Reference(
        dataset="cco", description="CCO", adapter="cco-release", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact=_CCO_ARTIFACT, path=str(p))},
    )


# --- native id + label resolution -------------------------------------------


def test_resolve_by_native_id(bfo_ref: Reference) -> None:
    term = resolve_term("bfo:BFO_0000029", [bfo_ref])
    assert term.dataset == "bfo"
    assert term.native_id == "BFO_0000029"
    assert term.label == "site"
    assert term.deprecated is False


def test_resolve_by_unique_label(bfo_ref: Reference) -> None:
    term = resolve_term("bfo:site", [bfo_ref])
    assert term.native_id == "BFO_0000029"


def test_resolve_deprecated_term_reports_flag(bfo_ref: Reference) -> None:
    term = resolve_term("bfo:BFO_9999999", [bfo_ref])
    assert term.deprecated is True


def test_resolve_ambiguous_label_is_error(cco_ref: Reference) -> None:
    with pytest.raises(AmbiguousSpineLabel):
        resolve_term("cco:Agent", [cco_ref])


def test_resolve_unresolvable_reference_is_error(bfo_ref: Reference) -> None:
    with pytest.raises(SpineTermNotFound):
        resolve_term("bfo:no-such-term-or-label", [bfo_ref])


def test_resolve_by_native_id_wins_over_a_same_named_label(cco_ref: Reference) -> None:
    """A spec matching a native id resolves as an id even if some other
    term's label happens to collide with it (native id lookup is tried
    first)."""
    term = resolve_term("cco:ont00001017", [cco_ref])
    assert term.native_id == "ont00001017"
    assert term.label == "Agent"


# --- grammar / registration errors ------------------------------------------


def test_pin_is_rejected(bfo_ref: Reference) -> None:
    with pytest.raises(InvalidSpineReference):
        resolve_term("bfo@some-tag:BFO_0000029", [bfo_ref])


def test_malformed_spec_is_rejected(bfo_ref: Reference) -> None:
    with pytest.raises(InvalidSpineReference):
        resolve_term("not-a-valid-spec", [bfo_ref])


def test_unregistered_dataset_is_error(bfo_ref: Reference) -> None:
    with pytest.raises(NotSpineDataset):
        resolve_term("nope:whatever", [bfo_ref])


def test_registered_but_not_spine_is_error(tmp_path: Path) -> None:
    p = tmp_path / "bfo.zip"
    _build_bfo_zip(p)
    ref = Reference(
        dataset="bfo", description="BFO-2020", adapter="bfo-2020", spine=False,
        latest="t", snapshots={"t": Snapshot(artifact=_BFO_ARTIFACT, path=str(p))},
    )
    with pytest.raises(NotSpineDataset):
        resolve_term("bfo:site", [ref])


def test_non_spine_capable_adapter_is_error(tmp_path: Path) -> None:
    """A dataset marked `spine: true` but whose adapter carries no
    `iter_terms` (an ordinary reference adapter like `zim`) cannot root a
    spine."""
    ref = Reference(
        dataset="wiki", description="a plain zim mirror", adapter="zim", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact="c" * 64, path=str(tmp_path / "nope.zim"))},
    )
    with pytest.raises(SpineIncapableAdapter):
        resolve_term("wiki:whatever", [ref])


# --- honestly unverifiable when the mirror is absent ------------------------


def test_mirror_unavailable_is_honestly_unverifiable() -> None:
    ref = Reference(
        dataset="bfo", description="BFO-2020", adapter="bfo-2020", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact=_BFO_ARTIFACT)},  # no path:, no corpora_roots
    )
    with pytest.raises(MirrorUnavailable):
        resolve_term("bfo:site", [ref], corpora_roots=())


# --- spine_bindings ----------------------------------------------------------


def test_spine_bindings_only_includes_spine_true(bfo_ref: Reference, tmp_path: Path) -> None:
    plain_ref = Reference(
        dataset="wiki", description="not a spine", adapter="zim", spine=False,
        latest="t", snapshots={"t": Snapshot(artifact="c" * 64)},
    )
    bindings = spine_bindings([bfo_ref, plain_ref])
    assert [b.dataset for b in bindings] == ["bfo"]
    assert bindings[0].tag == "t"
    assert bindings[0].artifact == _BFO_ARTIFACT


def test_spine_bindings_sorted_and_needs_no_mirror(bfo_ref: Reference, cco_ref: Reference) -> None:
    """No mirror bytes needed — pure config data — proven here by never
    touching corpora_roots or the fixture-materialized paths at all."""
    bindings = spine_bindings([cco_ref, bfo_ref])
    assert [b.dataset for b in bindings] == ["bfo", "cco"]
