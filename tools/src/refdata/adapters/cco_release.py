"""The `cco-release` spine format adapter — resolves native ids and labels
against a Common Core Ontologies release archive (spec/ledger.md §15.2). No
optional dependency: stdlib `zipfile` + `re` only.

**Format note (deviation from a plain XML read).** A CCO release
(github.com/CommonCoreOntology/CommonCoreOntologies) ships its merged,
stand-alone ontology — "the eleven mid-level Common Core Ontologies plus
BFO" — at `src/cco-iris/{date}/CommonCoreOntologiesMerged.ttl`
(the release-tagged copy; both the repo's commit-hash directory prefix and
the date subdirectory vary per release, so the member is located by suffix).
Unlike BFO-2020, a CCO release carries **no OWL/RDF-XML serialization at
all** for this file — Turtle only. Parsing full Turtle would mean a new
dependency (`rdflib`), which this adapter may not take on. What the release
actually emits is ROBOT's very regular block form: one `###  <IRI>` comment
line followed by that entity's whole `<IRI> rdf:type owl:Xxx ; pred obj ;
… .` statement, blank-line separated. This module exploits exactly that
regularity with a small, purpose-built block scanner (`re`, not a general
Turtle grammar) — never a generic parser, and it does not attempt to
understand Turtle beyond this one predictable shape. Terms are scoped to the
CCO namespace (`https://www.commoncoreontologies.org/`) only — the merged
file's bundled BFO terms are deliberately excluded here so `cco:` labels
never collide with `bfo:`'s own; an instance registering both datasets
resolves BFO material through the `bfo-2020` adapter instead.
"""

from __future__ import annotations

import re
import zipfile
from collections.abc import Iterator
from functools import lru_cache
from pathlib import Path

from ..errors import MirrorCorrupt
from . import AdapterResult, AdapterSearchHit
from ._spine_common import Entry, Handle
from ._spine_common import iter_terms as _iter_terms
from ._spine_common import resolve_entry as _resolve_entry
from ._spine_common import search_entries as _search_entries

_MERGED_RE = re.compile(r"(^|/)src/cco-iris/[^/]+/CommonCoreOntologiesMerged\.ttl$")
_CCO_NS = "https://www.commoncoreontologies.org/"

_BLOCK_HEADER_RE = re.compile(r"^###  (\S+)$", re.MULTILINE)
_LABEL_RE = re.compile(r'rdfs:label\s+"((?:[^"\\]|\\.)*)"@en')
_DEFINITION_RE = re.compile(
    r'<http://www\.w3\.org/2004/02/skos/core#definition>\s+"((?:[^"\\]|\\.)*)"@en'
)
_DEPRECATED_RE = re.compile(r'owl:deprecated\s+"?true"?')
_TERM_TYPES = frozenset({"Class", "ObjectProperty", "DatatypeProperty", "NamedIndividual"})

_UNESCAPE_RE = re.compile(r'\\(.)')
_UNESCAPE_MAP = {'"': '"', "\\": "\\", "n": "\n", "t": "\t", "r": "\r", "'": "'"}


def available() -> bool:
    return True


def _find_member(zf: zipfile.ZipFile) -> str:
    candidates = [n for n in zf.namelist() if _MERGED_RE.search(n)]
    if not candidates:
        raise MirrorCorrupt(
            "no src/cco-iris/*/CommonCoreOntologiesMerged.ttl entry in this CCO "
            "release archive"
        )
    return sorted(candidates, key=len)[0]


def _unescape(s: str) -> str:
    return _UNESCAPE_RE.sub(lambda m: _UNESCAPE_MAP.get(m.group(1), m.group(1)), s)


def _iter_blocks(text: str) -> Iterator[tuple[str, str]]:
    """Yield `(header_iri, block_text)` for each `###  <IRI>` comment-headed
    entity block — the ROBOT-emitted grain this scanner relies on."""
    headers = list(_BLOCK_HEADER_RE.finditer(text))
    for i, m in enumerate(headers):
        start = m.end()
        end = headers[i + 1].start() if i + 1 < len(headers) else len(text)
        yield m.group(1), text[start:end]


def _entity_type(header_iri: str, block: str) -> str | None:
    """The entity's own `rdf:type owl:Xxx`, anchored to its own IRI as
    subject — never a nested blank node's (a restriction's `[ rdf:type
    owl:Restriction ; … ]` has no preceding `<IRI>`, so it can't match)."""
    m = re.search(re.escape(f"<{header_iri}>") + r"\s+rdf:type\s+owl:(\w+)", block)
    return m.group(1) if m else None


@lru_cache(maxsize=8)
def _parse(mirror_path_str: str) -> Handle:
    try:
        with zipfile.ZipFile(mirror_path_str) as zf:
            member = _find_member(zf)
            data = zf.read(member)
    except zipfile.BadZipFile as exc:
        raise MirrorCorrupt(f"{mirror_path_str}: {exc}") from exc
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise MirrorCorrupt(f"{mirror_path_str}: {member} is not valid UTF-8: {exc}") from exc

    by_id: dict[str, Entry] = {}
    for header_iri, block in _iter_blocks(text):
        if not header_iri.startswith(_CCO_NS):
            continue
        owl_type = _entity_type(header_iri, block)
        if owl_type not in _TERM_TYPES:
            continue
        native_id = header_iri[len(_CCO_NS):]
        label_m = _LABEL_RE.search(block)
        def_m = _DEFINITION_RE.search(block)
        by_id[native_id] = Entry(
            native_id=native_id,
            label=_unescape(label_m.group(1)) if label_m else None,
            definition=_unescape(def_m.group(1)) if def_m else None,
            deprecated=bool(_DEPRECATED_RE.search(block)),
        )
    if not by_id:
        raise MirrorCorrupt(
            f"{mirror_path_str}: {member} carried no {_CCO_NS}-namespaced terms"
        )
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
    """The conformance gate's own seam (spec/ledger.md §15.7): extract the
    release's merged Turtle ontology file (`_find_member`'s `_MERGED_RE`
    match — already-valid Turtle/OWL on its own, no conversion needed) out
    of the zip into `work_dir`, so a standard OWL 2 reasoner can read the
    spine's axioms as a file on disk beside the export. Raises
    `MirrorCorrupt` exactly as `open_archive` does when the archive carries
    no merged file (callers — `ledger.export.spine_payloads` — catch this
    and degrade to a report note, never a crash)."""
    with zipfile.ZipFile(archive_path) as zf:
        member = _find_member(zf)
        data = zf.read(member)
    work_dir.mkdir(parents=True, exist_ok=True)
    out_path = work_dir / "cco-merged.ttl"
    out_path.write_bytes(data)
    return [out_path]
