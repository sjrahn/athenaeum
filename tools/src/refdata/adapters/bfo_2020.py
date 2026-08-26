"""The `bfo-2020` spine format adapter — resolves native ids and labels
against a BFO-2020 release archive (spec/ledger.md §15.2). No optional
dependency: a BFO-2020 release zip (the GitHub codeload archive of
github.com/BFO-ontology/BFO-2020) ships its OWL/RDF-XML class-and-relation
table at `21838-2/owl/bfo-core.owl` — the actual layout found under a real
release's top-level `{repo}-{ref}/` directory (which varies by tag/commit, so
the member is located by suffix, not a hardcoded prefix) — parsed with the
stdlib `xml.etree.ElementTree`.

Every `owl:Class`/`owl:ObjectProperty`/`owl:AnnotationProperty`/
`owl:DatatypeProperty`/`owl:NamedIndividual` that is a DIRECT child of the
document root is one term: native id is the IRI's final `/`-segment (e.g.
`http://purl.obolibrary.org/obo/BFO_0000029` -> `BFO_0000029`, BFO's own
native identity, distinct from the human `[029-BFO]`-style tag the
documentation tables use), label is `rdfs:label`, definition is
`skos:definition` (the elucidation/definition text BFO actually carries),
deprecation is a present `owl:deprecated` element reading `"true"`. Anonymous
classes nested inside restrictions (`owl:Restriction`/`owl:unionOf` blank
nodes) are never direct children of the root, so `findall` with no `.//`
prefix naturally excludes them — only the ontology's own declared terms.
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
import zipfile
from functools import lru_cache
from pathlib import Path

from ..errors import MirrorCorrupt
from . import AdapterResult, AdapterSearchHit
from ._spine_common import Entry, Handle
from ._spine_common import iter_terms as _iter_terms
from ._spine_common import resolve_entry as _resolve_entry
from ._spine_common import search_entries as _search_entries

_MEMBER_SUFFIX = "21838-2/owl/bfo-core.owl"

_RDF_NS = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
_NS = {
    "owl": "http://www.w3.org/2002/07/owl#",
    "rdfs": "http://www.w3.org/2000/01/rdf-schema#",
    "skos": "http://www.w3.org/2004/02/skos/core#",
}
_RDF_ABOUT = f"{{{_RDF_NS}}}about"
_TERM_TAGS = (
    "owl:Class",
    "owl:ObjectProperty",
    "owl:AnnotationProperty",
    "owl:DatatypeProperty",
    "owl:NamedIndividual",
)


def available() -> bool:
    return True


def _find_member(zf: zipfile.ZipFile) -> str:
    candidates = [n for n in zf.namelist() if n.endswith(_MEMBER_SUFFIX)]
    if not candidates:
        raise MirrorCorrupt(
            f"no {_MEMBER_SUFFIX} entry in this BFO-2020 release archive — "
            "expected the standard 21838-2/owl/bfo-core.owl table"
        )
    return sorted(candidates, key=len)[0]


def _local_id(iri: str) -> str:
    return iri.rsplit("/", 1)[-1]


def _text(el: ET.Element | None) -> str | None:
    if el is None or el.text is None:
        return None
    stripped = el.text.strip()
    return stripped or None


@lru_cache(maxsize=8)
def _parse(mirror_path_str: str) -> Handle:
    try:
        with zipfile.ZipFile(mirror_path_str) as zf:
            member = _find_member(zf)
            data = zf.read(member)
    except zipfile.BadZipFile as exc:
        raise MirrorCorrupt(f"{mirror_path_str}: {exc}") from exc

    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise MirrorCorrupt(f"{mirror_path_str}: {member} did not parse as XML: {exc}") from exc

    by_id: dict[str, Entry] = {}
    for tag in _TERM_TAGS:
        for el in root.findall(tag, _NS):
            about = el.get(_RDF_ABOUT)
            if not about:
                continue
            native_id = _local_id(about)
            deprecated_el = el.find("owl:deprecated", _NS)
            deprecated = (_text(deprecated_el) or "").lower() == "true"
            by_id[native_id] = Entry(
                native_id=native_id,
                label=_text(el.find("rdfs:label", _NS)),
                definition=_text(el.find("skos:definition", _NS)),
                deprecated=deprecated,
            )
    if not by_id:
        raise MirrorCorrupt(f"{mirror_path_str}: {member} carried no recognized owl terms")
    return Handle(by_id=by_id)


def open_archive(mirror_path: Path) -> Handle:
    return _parse(str(mirror_path.resolve()))


def resolve_entry(handle: Handle, native_id: str) -> AdapterResult:
    return _resolve_entry(handle, native_id)


def search_entries(
    handle: Handle, query: str, limit: int, mode: str = "blend"
) -> list[AdapterSearchHit]:
    return _search_entries(handle, query, limit, mode=mode)


def iter_terms(handle: Handle):
    return _iter_terms(handle)


def ontology_payload_paths(archive_path: Path, work_dir: Path) -> list[Path]:
    """The conformance gate's own seam (spec/ledger.md §15.7): extract this
    release's reasoner-consumable OWL/RDF-XML table (`_MEMBER_SUFFIX`,
    already-valid OWL on its own) out of the zip into `work_dir` — a
    standard OWL 2 reasoner needs the spine's axioms as a file on disk
    beside the export, not merely resolvable through `iter_terms`. Reuses
    `_find_member` rather than re-locating the entry; raises `MirrorCorrupt`
    exactly as `open_archive` does when the archive carries none (callers —
    `ledger.export.spine_payloads` — catch this and degrade to a report note,
    never a crash)."""
    with zipfile.ZipFile(archive_path) as zf:
        member = _find_member(zf)
        data = zf.read(member)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / "bfo-core.owl"
    out_path.write_bytes(data)
    return [out_path]
