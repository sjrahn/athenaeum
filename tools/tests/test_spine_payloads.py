"""Filling the conformance gate's `spine_paths` seam (spec/ledger.md §15.7,
ISO/IEC 21838-1 Annex D.5.1): the two spine adapters' `ontology_payload_paths`
extraction, `ledger.export.spine_payloads`'s materialize-then-extract sweep
(happy path + every honestly-degraded skip), and `gate_owner_export`'s
coverage caveat when a registered spine dataset couldn't be included."""

from __future__ import annotations

import stat
import textwrap
import zipfile
from pathlib import Path

import pytest

from ath.manifest import Reference, Snapshot
from ledger.export import GateResult, gate_owner_export, spine_payloads
from refdata.adapters import bfo_2020, cco_release

_BFO_OWL = """<?xml version="1.0"?>
<rdf:RDF xmlns="http://purl.obolibrary.org/obo/bfo/"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns:owl="http://www.w3.org/2002/07/owl#"
     xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
     xmlns:skos="http://www.w3.org/2004/02/skos/core#">
    <owl:Class rdf:about="http://purl.obolibrary.org/obo/BFO_0000029">
        <rdfs:label xml:lang="en">site</rdfs:label>
    </owl:Class>
</rdf:RDF>
"""

_CCO_TTL = """\
@prefix owl: <http://www.w3.org/2002/07/owl#> .
@prefix rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> .
@prefix rdfs: <http://www.w3.org/2000/01/rdf-schema#> .

###  https://www.commoncoreontologies.org/ont00001017
<https://www.commoncoreontologies.org/ont00001017> rdf:type owl:Class ;
  rdfs:label "Agent"@en .
"""

_BFO_ARTIFACT = "a" * 64
_CCO_ARTIFACT = "b" * 64
_SAMPLE_TEXT = "@prefix owl: <http://www.w3.org/2002/07/owl#> .\n<ledger://x> a owl:Class .\n"


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


# --------------------------------------------------------- adapter extraction


def test_bfo_ontology_payload_paths_extracts_owl_file(tmp_path: Path) -> None:
    zip_path = tmp_path / "bfo.zip"
    _build_bfo_zip(zip_path)
    out = bfo_2020.ontology_payload_paths(zip_path, tmp_path / "out")
    assert len(out) == 1
    assert out[0].is_file()
    assert out[0].read_bytes() == _BFO_OWL.encode("utf-8")


def test_cco_ontology_payload_paths_extracts_ttl_file(tmp_path: Path) -> None:
    zip_path = tmp_path / "cco.zip"
    _build_cco_zip(zip_path)
    out = cco_release.ontology_payload_paths(zip_path, tmp_path / "out")
    assert len(out) == 1
    assert out[0].is_file()
    assert out[0].read_bytes() == _CCO_TTL.encode("utf-8")


def test_bfo_ontology_payload_paths_raises_on_missing_member(tmp_path: Path) -> None:
    from refdata.errors import MirrorCorrupt

    zip_path = tmp_path / "empty.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("nothing-here.txt", "x")
    with pytest.raises(MirrorCorrupt):
        bfo_2020.ontology_payload_paths(zip_path, tmp_path / "out")


# --------------------------------------------------------------- spine_payloads


@pytest.fixture
def bfo_ref(tmp_path: Path) -> Reference:
    p = tmp_path / "bfo.zip"
    _build_bfo_zip(p)
    return Reference(
        dataset="bfo", description="BFO-2020", adapter="bfo-2020", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact=_BFO_ARTIFACT, path=str(p))},
    )


def test_spine_payloads_happy_path(bfo_ref: Reference, tmp_path: Path) -> None:
    paths, notes = spine_payloads([bfo_ref], [], tmp_path / "work")
    assert not notes
    assert len(paths) == 1
    assert paths[0].read_bytes() == _BFO_OWL.encode("utf-8")


def test_spine_payloads_ignores_non_spine_references(tmp_path: Path) -> None:
    plain = Reference(
        dataset="wiki", description="not a spine", adapter="zim", spine=False,
        latest="t", snapshots={"t": Snapshot(artifact="c" * 64)},
    )
    paths, notes = spine_payloads([plain], [], tmp_path / "work")
    assert paths == []
    assert notes == []


def test_spine_payloads_notes_unmaterialized_mirror(tmp_path: Path) -> None:
    ref = Reference(
        dataset="bfo", description="BFO-2020", adapter="bfo-2020", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact=_BFO_ARTIFACT)},  # no path:, no roots
    )
    paths, notes = spine_payloads([ref], [], tmp_path / "work")
    assert paths == []
    assert len(notes) == 1
    assert "not materialized" in notes[0]
    assert "bfo" in notes[0]


def test_spine_payloads_notes_adapter_without_payload_fn(tmp_path: Path) -> None:
    ref = Reference(
        dataset="wiki-spine", description="misregistered", adapter="zim", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact="c" * 64, path=str(tmp_path / "x.zim"))},
    )
    (tmp_path / "x.zim").write_bytes(b"not a real zim")
    paths, notes = spine_payloads([ref], [], tmp_path / "work")
    assert paths == []
    assert len(notes) == 1
    assert "ontology_payload_paths" in notes[0]


def test_spine_payloads_notes_corrupt_archive(tmp_path: Path) -> None:
    p = tmp_path / "bfo.zip"
    p.write_bytes(b"not actually a zip")
    ref = Reference(
        dataset="bfo", description="BFO-2020", adapter="bfo-2020", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact=_BFO_ARTIFACT, path=str(p))},
    )
    paths, notes = spine_payloads([ref], [], tmp_path / "work")
    assert paths == []
    assert len(notes) == 1
    assert "extraction failed" in notes[0]


# ------------------------------------------------------------ gate_owner_export


def _write_fake_robot(bin_dir: Path, *, exit_code: int, argv_log: Path) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    script = bin_dir / "robot"
    script.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        printf '%s\\n' "$@" > "{argv_log}"
        exit {exit_code}
    """), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)


def test_gate_owner_export_passes_spine_payloads_as_extra_inputs(
    bfo_ref: Reference, tmp_path: Path, monkeypatch,
) -> None:
    bin_dir = tmp_path / "bin"
    argv_log = tmp_path / "argv.log"
    _write_fake_robot(bin_dir, exit_code=0, argv_log=argv_log)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv("ATHENAEUM_REASONER", raising=False)

    result, notes = gate_owner_export(_SAMPLE_TEXT, [bfo_ref], [], work_dir=tmp_path / "gate")
    assert result.status == "passed"
    assert not notes
    assert "[spine" not in result.detail  # full coverage — no caveat needed
    logged = argv_log.read_text(encoding="utf-8")
    assert "bfo-core.owl" in logged


def test_gate_owner_export_caveats_detail_when_spine_skipped(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    argv_log = tmp_path / "argv.log"
    _write_fake_robot(bin_dir, exit_code=0, argv_log=argv_log)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv("ATHENAEUM_REASONER", raising=False)

    unmaterialized = Reference(
        dataset="bfo", description="BFO-2020", adapter="bfo-2020", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact=_BFO_ARTIFACT)},
    )
    result, notes = gate_owner_export(_SAMPLE_TEXT, [unmaterialized], [],
                                      work_dir=tmp_path / "gate")
    assert result.status == "passed"
    assert len(notes) == 1
    assert "not materialized" in notes[0]
    assert result.detail.startswith("[spine not included")


def test_gate_owner_export_no_spine_registered_no_caveat(tmp_path: Path, monkeypatch) -> None:
    bin_dir = tmp_path / "bin"
    argv_log = tmp_path / "argv.log"
    _write_fake_robot(bin_dir, exit_code=0, argv_log=argv_log)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv("ATHENAEUM_REASONER", raising=False)

    result, notes = gate_owner_export(_SAMPLE_TEXT, [], [], work_dir=tmp_path / "gate")
    assert result.status == "passed"
    assert notes == []
    assert "[spine" not in result.detail


def test_gate_owner_export_returns_a_gate_result(tmp_path: Path) -> None:
    result, notes = gate_owner_export(_SAMPLE_TEXT, [], [], work_dir=tmp_path / "gate")
    assert isinstance(result, GateResult)
    assert isinstance(notes, list)
