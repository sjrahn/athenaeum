"""The `bfo-2020` spine format adapter (spec/ledger.md §15.2): resolution
against a tiny synthetic BFO-2020-shaped release archive — a zip carrying
`.../21838-2/owl/bfo-core.owl`, the real release's OWL/RDF-XML class-and-
relation table. No optional dependency (stdlib `zipfile` + `xml.etree`
only), so this needs no importorskip guard, unlike zim/osm_pbf.
"""

from __future__ import annotations

import zipfile
from pathlib import Path

from refdata.adapters import adapter_available, bfo_2020
from refdata.errors import EntryNotFound

_OWL = """<?xml version="1.0"?>
<rdf:RDF xmlns="http://purl.obolibrary.org/obo/bfo/"
     xmlns:rdf="http://www.w3.org/1999/02/22-rdf-syntax-ns#"
     xmlns:owl="http://www.w3.org/2002/07/owl#"
     xmlns:rdfs="http://www.w3.org/2000/01/rdf-schema#"
     xmlns:skos="http://www.w3.org/2004/02/skos/core#">
    <owl:Class rdf:about="http://purl.obolibrary.org/obo/BFO_0000001">
        <rdfs:label xml:lang="en">entity</rdfs:label>
        <skos:definition xml:lang="en">An entity is anything that exists.</skos:definition>
    </owl:Class>
    <owl:Class rdf:about="http://purl.obolibrary.org/obo/BFO_0000029">
        <rdfs:subClassOf>
            <owl:Restriction>
                <owl:onProperty rdf:resource="http://purl.obolibrary.org/obo/BFO_0000050"/>
                <owl:allValuesFrom>
                    <owl:Class>
                        <owl:unionOf rdf:parseType="Collection">
                            <rdf:Description rdf:about="http://purl.obolibrary.org/obo/BFO_0000029"/>
                        </owl:unionOf>
                    </owl:Class>
                </owl:allValuesFrom>
            </owl:Restriction>
        </rdfs:subClassOf>
        <rdfs:label xml:lang="en">site</rdfs:label>
        <skos:definition xml:lang="en">A three-dimensional immaterial entity.</skos:definition>
    </owl:Class>
    <owl:Class rdf:about="http://purl.obolibrary.org/obo/BFO_9999999">
        <rdfs:label xml:lang="en">obsolete thing</rdfs:label>
        <owl:deprecated>true</owl:deprecated>
    </owl:Class>
    <owl:ObjectProperty rdf:about="http://purl.obolibrary.org/obo/BFO_0000050">
        <rdfs:label xml:lang="en">part of</rdfs:label>
    </owl:ObjectProperty>
</rdf:RDF>
"""


def _build_zip(path: Path, *, prefix: str = "BFO-2020-master") -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr(f"{prefix}/21838-2/owl/bfo-core.owl", _OWL)


def _handle(tmp_path: Path, *, prefix: str = "BFO-2020-master"):
    p = tmp_path / "bfo.zip"
    _build_zip(p, prefix=prefix)
    return bfo_2020.open_archive(p)


def test_adapter_registered_and_available() -> None:
    assert adapter_available("bfo-2020") is True


def test_resolve_by_native_id(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    result = bfo_2020.resolve_entry(handle, "BFO_0000029")
    assert result.canonical_id == "BFO_0000029"
    assert result.title == "site"
    assert "site" in result.text
    assert "immaterial entity" in result.text
    assert result.content_type == "text/plain"


def test_entry_not_found(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    try:
        bfo_2020.resolve_entry(handle, "BFO_no-such-term")
    except EntryNotFound:
        pass
    else:
        raise AssertionError("expected EntryNotFound")


def test_iter_terms_reports_all_terms_with_deprecated_flag(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    terms = {t.native_id: t for t in bfo_2020.iter_terms(handle)}
    assert set(terms) == {"BFO_0000001", "BFO_0000029", "BFO_9999999", "BFO_0000050"}
    assert terms["BFO_0000029"].label == "site"
    assert terms["BFO_0000029"].deprecated is False
    assert terms["BFO_9999999"].deprecated is True
    # the object property is enumerated too — spine roots both classes and relations
    assert terms["BFO_0000050"].label == "part of"


def test_anonymous_restriction_classes_are_not_enumerated(tmp_path: Path) -> None:
    """The nested `owl:Class`/`owl:unionOf` blank node inside `site`'s
    restriction must never surface as its own term — only direct children of
    the document root are terms."""
    handle = _handle(tmp_path)
    terms = list(bfo_2020.iter_terms(handle))
    assert all(t.native_id for t in terms)
    assert len(terms) == 4


def test_search_entries_label_and_definition(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    suggest_hits = bfo_2020.search_entries(handle, "site", 10, mode="suggest")
    assert any(h.native_id == "BFO_0000029" for h in suggest_hits)

    fulltext_hits = bfo_2020.search_entries(handle, "immaterial", 10, mode="fulltext")
    assert any(h.native_id == "BFO_0000029" for h in fulltext_hits)
    # a label-only match doesn't show up in fulltext-only mode for a word not in its definition
    assert bfo_2020.search_entries(handle, "part of", 10, mode="fulltext") == []


def test_search_invalid_mode_raises(tmp_path: Path) -> None:
    handle = _handle(tmp_path)
    try:
        bfo_2020.search_entries(handle, "site", 10, mode="bogus")
    except ValueError:
        pass
    else:
        raise AssertionError("expected ValueError")


def test_member_located_by_suffix_regardless_of_top_level_prefix(tmp_path: Path) -> None:
    """A real release's top-level directory name varies by tag/commit — the
    member is found by suffix, not a hardcoded prefix."""
    handle = _handle(tmp_path, prefix="BFO-ontology-BFO-2020-abcd123")
    result = bfo_2020.resolve_entry(handle, "BFO_0000001")
    assert result.title == "entity"
