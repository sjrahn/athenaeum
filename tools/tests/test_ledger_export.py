"""`ath ledger export` — the v39 RDF projection (spec/ledger.md §15.7):
the assertion map (confirmed asserts + reifies, reported describes-only),
presence claims (reifier-only, no triple), conditional-domain claims (never
assert, on any plane), fail-closed plane projection (a private-backed fact
vanishes entirely on the public plane), the lineage deprecation pattern, a
schema's `extends:` subclass chain into a registered spine, the
reproducibility stamp, and byte-identical determinism across repeated runs.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import frontmatter
import pytest

from ath.manifest import Instance, Reference, Snapshot
from corpus import paths as corpus_paths
from corpus import records as corpus_records
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.export import IAO_TERM_REPLACED_BY, PROV, RDF, export_ledger

H_PUB = "a" * 64
H_PRIV = "b" * 64
BFO_ARTIFACT = "9" * 64

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
</rdf:RDF>
"""


def _build_bfo_zip(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("BFO-2020-master/21838-2/owl/bfo-core.owl", _BFO_OWL)


def _mk_record(corpus_root: Path, h: str, *, public: bool) -> None:
    post = frontmatter.Post(
        content="body text",
        **corpus_records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0"),
    )
    corpus_records.set_artifact_block(post, mime="text/plain", fields={})
    if public:
        corpus_records.append_origin_block(
            post, uri="https://openhost.example/x", snapshot="2026-01-01T00:00:00Z",
            schema_id="openhost",
        )
    corpus_records.dump(post, corpus_paths.record_path(corpus_root, h))


def _write_json(path: Path, obj: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2), encoding="utf-8")


@pytest.fixture
def ledger(tmp_path: Path):
    root = tmp_path
    corpus_root = root / "corpus"
    (corpus_root / "schema" / "origin").mkdir(parents=True)
    (corpus_root / "schema" / "origin" / "openhost.yaml").write_text(
        "tenancy: public\n", encoding="utf-8"
    )
    _mk_record(corpus_root, H_PUB, public=True)
    _mk_record(corpus_root, H_PRIV, public=False)

    ledger_root = root / "ledger"
    (ledger_root / "schemas").mkdir(parents=True)
    (ledger_root / "schemas" / "thing.yaml").write_text(
        'type: thing\ndescription: a test concept\nextends: "bfo:BFO_0000029"\n',
        encoding="utf-8",
    )

    _write_json(ledger_root / "facts" / "thing" / "public-thing.json", {
        "id": "public-thing", "type": "thing", "name": "Public Thing",
        "sources": {"s1": {"record": H_PUB}},
        "claims": [
            {
                "id": "public-thing:colour", "predicate": "colour", "value": "red",
                "status": "confirmed", "asof": "2026-08-25",
                "evidence": [{"source": "s1", "kind": "authoritative", "quote": "red thing"}],
            },
            {
                "id": "public-thing:likes", "predicate": "liked-by", "value": "allegedly the best",
                "status": "reported", "asof": "2026-08-01",
                "qualifiers": {"attribution": "a fan"},
                "evidence": [{"source": "s1", "kind": "direct"}],
            },
            {
                "id": "public-thing:sibling", "predicate": "sibling",
                "presence": "none", "status": "confirmed", "asof": "2026-08-25",
                "evidence": [{"source": "s1", "kind": "authoritative"}],
            },
        ],
    })

    _write_json(ledger_root / "facts" / "thing" / "private-thing.json", {
        "id": "private-thing", "type": "thing", "name": "Private Thing",
        "sources": {"s1": {"record": H_PRIV}},
        "claims": [{
            "id": "private-thing:colour", "predicate": "colour", "value": "blue",
            "status": "confirmed", "asof": "2026-08-25",
            "evidence": [{"source": "s1", "kind": "authoritative"}],
        }],
    })

    _write_json(ledger_root / "facts" / "continuity" / "some-universe.json", {
        "id": "some-universe", "type": "continuity", "name": "Some Universe",
        "ontology": {"commitment": "conditional"},
    })

    _write_json(ledger_root / "facts" / "character" / "some-char.json", {
        "id": "some-char", "type": "character", "name": "Some Character",
        "domain": "some-universe",
        "sources": {"s1": {"record": H_PUB}},
        "claims": [{
            "id": "some-char:commands", "predicate": "commands", "object": "public-thing",
            "status": "confirmed", "asof": "2026-08-25",
            "evidence": [{"source": "s1", "kind": "direct"}],
        }],
    })

    _write_json(ledger_root / "facts" / "LINEAGE.json", {
        "old-thing": {"to": "public-thing", "reason": "renamed"},
        "old-private": {"to": "private-thing", "reason": "merged"},
    })

    bfo_zip = root / "bfo.zip"
    _build_bfo_zip(bfo_zip)
    bfo_ref = Reference(
        dataset="bfo", description="BFO-2020", adapter="bfo-2020", spine=True,
        latest="t", snapshots={"t": Snapshot(artifact=BFO_ARTIFACT, path=str(bfo_zip))},
    )
    datasets = {"bfo": bfo_ref}

    join = CorpusJoin([RegisteredCorpus(name="corpus", root=corpus_root, private=True)])
    instance = Instance(root=root, name="test", visibility="private", tiers=(), audiences={})
    return ledger_root, join, datasets, instance


def _export(ledger, plane: str = "owner"):
    ledger_root, join, datasets, instance = ledger
    return export_ledger(ledger_root, join, datasets, instance, plane=plane)


# --------------------------------------------------------------- assertion map


def test_confirmed_claim_asserts_and_reifies(ledger) -> None:
    text, _ = _export(ledger)
    subj, pred, obj = "<ledger://public-thing>", "<ledger://predicate/colour>", '"red"'
    assert f"{subj} {pred} {obj} ." in text.splitlines()
    reifier = "<ledger://public-thing#colour>"
    triple_term = f"<<( {subj} {pred} {obj} )>>"
    assert f"{reifier} <{RDF}reifies> {triple_term} ." in text.splitlines()
    assert f'{reifier} <ledger://meta/status> "confirmed" .' in text.splitlines()
    assert (f'{reifier} <ledger://meta/asof> '
            f'"2026-08-25"^^<http://www.w3.org/2001/XMLSchema#date> .') in text.splitlines()
    assert f"{reifier} <{PROV}wasQuotedFrom> <corpus://{H_PUB}> ." in text.splitlines()


def test_reported_claim_describes_only_never_asserts(ledger) -> None:
    text, _ = _export(ledger)
    lines = text.splitlines()
    naked = '<ledger://public-thing> <ledger://predicate/liked-by> "allegedly the best" .'
    assert naked not in lines
    reifier = "<ledger://public-thing#likes>"
    triple_term = ('<<( <ledger://public-thing> <ledger://predicate/liked-by> '
                   '"allegedly the best" )>>')
    assert f"{reifier} <{RDF}reifies> {triple_term} ." in lines
    assert f'{reifier} <ledger://meta/status> "reported" .' in lines
    assert f'{reifier} <ledger://predicate/qualifier-attribution> "a fan" .' in lines


def test_presence_claim_is_reifier_only_no_triple(ledger) -> None:
    text, _ = _export(ledger)
    lines = text.splitlines()
    reifier = "<ledger://public-thing#sibling>"
    assert f"{reifier} a <ledger://meta/PresenceClaim> ." in lines
    assert f"{reifier} <ledger://meta/aboutFact> <ledger://public-thing> ." in lines
    assert f"{reifier} <ledger://meta/onPredicate> <ledger://predicate/sibling> ." in lines
    assert f'{reifier} <ledger://meta/presence> "none" .' in lines
    # No triple term, no rdf:reifies — there is no triple to reify (§5.5/§15.7).
    assert not any(line.startswith(reifier) and "reifies" in line for line in lines)


def test_conditional_domain_claim_never_asserts(ledger) -> None:
    text, report = _export(ledger)
    lines = text.splitlines()
    subj, pred, obj = "<ledger://some-char>", "<ledger://predicate/commands>", "<ledger://public-thing>"
    naked = f"{subj} {pred} {obj} ."
    assert naked not in lines
    reifier = "<ledger://some-char#commands>"
    triple_term = f"<<( {subj} {pred} {obj} )>>"
    assert f"{reifier} <{RDF}reifies> {triple_term} ." in lines
    # still described, status carried, whatever its rung
    assert f'{reifier} <ledger://meta/status> "confirmed" .' in lines
    assert not report.notes  # not a skip — a deliberate never-assert, not an error


# ------------------------------------------------------------------- planes


def test_public_plane_omits_private_backed_fact_entirely(ledger) -> None:
    text_pub, _ = _export(ledger, plane="public")
    assert "private-thing" not in text_pub
    assert "public-thing" in text_pub
    # a lineage row whose survivor is invisible on this plane is fail-closed too
    assert "old-private" not in text_pub
    assert "old-thing" in text_pub

    text_owner, _ = _export(ledger, plane="owner")
    assert "private-thing" in text_owner
    assert "old-private" in text_owner


def test_unknown_plane_is_export_error(ledger) -> None:
    from ledger.export import ExportError

    ledger_root, join, datasets, instance = ledger
    with pytest.raises(ExportError):
        export_ledger(ledger_root, join, datasets, instance, plane="nonsense")


# ------------------------------------------------------------------ lineage


def test_deprecation_pattern_for_lineage_row(ledger) -> None:
    text, _ = _export(ledger)
    lines = text.splitlines()
    old = "<ledger://old-thing>"
    assert f"{old} owl:deprecated true ." in lines
    assert f"{old} <{IAO_TERM_REPLACED_BY}> <ledger://public-thing> ." in lines


# --------------------------------------------------------------- vocabulary


def test_domain_minted_type_gets_qualified_class(ledger) -> None:
    """A type minted in a domain's own `ontology.types` (§15.4) gets the
    QUALIFIED class IRI on its instances and its own owl:Class + subClassOf
    declaration — exercising the real `ledger.ontology` closure machinery
    (`import_closure`/`domain_types`/`type_chain`), not just the plain
    shared-tier path every other fixture fact takes."""
    ledger_root, join, datasets, instance = ledger
    universe = json.loads(
        (ledger_root / "facts" / "continuity" / "some-universe.json").read_text())
    universe["ontology"]["types"] = {
        "vessel": {"extends": "bfo:BFO_0000029", "description": "an in-universe craft"}
    }
    _write_json(ledger_root / "facts" / "continuity" / "some-universe.json", universe)
    _write_json(ledger_root / "facts" / "vessel" / "galactica.json", {
        "id": "galactica", "type": "vessel", "name": "Galactica",
        "domain": "some-universe",
    })

    text, report = export_ledger(ledger_root, join, datasets, instance, plane="owner")
    lines = text.splitlines()
    assert "<ledger://galactica> a <ledger://type/some-universe/vessel> ." in lines
    assert "<ledger://type/some-universe/vessel> a owl:Class ." in lines
    assert ("<ledger://type/some-universe/vessel> rdfs:subClassOf "
            "<http://purl.obolibrary.org/obo/BFO_0000029> .") in lines
    assert not report.unverified_spine_refs


def test_subclass_chain_via_extends_into_spine(ledger) -> None:
    text, report = _export(ledger)
    lines = text.splitlines()
    assert "<ledger://type/thing> a owl:Class ." in lines
    assert ("<ledger://type/thing> rdfs:subClassOf "
            "<http://purl.obolibrary.org/obo/BFO_0000029> .") in lines
    assert not report.unverified_spine_refs


# ------------------------------------------------------------- reproducibility


def test_reproducibility_stamp_fields(ledger) -> None:
    text, report = _export(ledger)
    lines = text.splitlines()
    assert report.plane == "owner"
    assert report.instance_commit == ""  # tmp_path is not a git repo — "absent"
    assert report.spec_version > 0
    assert [b.dataset for b in report.spine] == ["bfo"]
    assert '<ledger://export> <ledger://meta/plane> "owner" .' in lines
    assert '<ledger://export> <ledger://meta/instanceCommit> "absent" .' in lines
    assert f'<ledger://export> <ledger://meta/specVersion> {report.spec_version} .' in lines
    assert f'<ledger://export> <ledger://meta/spineBinding> "bfo@t:{BFO_ARTIFACT}" .' in lines


# ------------------------------------------------------------------ determinism


def test_determinism_two_runs_byte_identical(ledger) -> None:
    text1, _ = _export(ledger)
    text2, _ = _export(ledger)
    assert text1 == text2


# ------------------------------------------------------------- IRI legality


def test_verbatim_uris_are_iri_escaped(ledger) -> None:
    """§6.1 functional-URI refs (raw `[…]`, raw spaces) are written
    percent-encoded inside `<…>` — RDF4J rejects the raw forms — and a
    read-side percent-decode recovers the stored bytes exactly."""
    from urllib.parse import unquote

    ledger_root, join, datasets, instance = ledger
    rough = f"corpus://{H_PUB}?path=The Black Lodge - General - x[3].json"
    _write_json(ledger_root / "facts" / "thing" / "rough.json", {
        "id": "rough", "type": "thing", "name": "Rough",
        "sources": {"s1": {"record": H_PUB}},
        "artifacts": [{"uri": rough, "role": "documents"}],
        "claims": [{
            "id": "rough:colour", "predicate": "colour", "value": "red",
            "status": "confirmed", "asof": "2026-08-25",
            "evidence": [{"source": "s1", "kind": "direct", "anchor": "el=quote[1-43]"}],
        }],
    })
    text, _ = export_ledger(ledger_root, join, datasets, instance, plane="owner")
    esc_roster = (f"corpus://{H_PUB}"
                  "?path=The%20Black%20Lodge%20-%20General%20-%20x%5B3%5D.json")
    esc_evidence = f"corpus://{H_PUB}?el=quote%5B1-43%5D"
    assert f"<{esc_roster}>" in text
    assert f"<{esc_evidence}>" in text
    assert rough not in text  # never written raw inside an IRIREF
    assert unquote(esc_roster) == rough


def test_iri_escape_percent_first_roundtrips() -> None:
    from urllib.parse import unquote

    from ledger.export import _iri_escape

    raw = f"corpus://{H_PUB}?path=100%_x [y].json"
    escaped = _iri_escape(raw)
    assert "%25" in escaped and " " not in escaped and "[" not in escaped
    assert unquote(escaped) == raw


# ----------------------------------------------------------------------- CLI


@pytest.fixture
def cli_root(ledger, tmp_path: Path) -> Path:
    """The same fixture content, wired up as a real on-disk instance
    (`athenaeum.yaml` + the `references:` registration) so `ledger._cli`'s
    `--root`/`find_root`/`load_instance` path is exercised end to end,
    matching every other command's own CLI-level test coverage."""
    ledger_root, _, _, _ = ledger
    root = ledger_root.parent
    (root / "athenaeum.yaml").write_text(
        "name: testeum\n"
        "visibility: private\n"
        "references:\n"
        "  bfo:\n"
        "    description: BFO-2020\n"
        "    adapter: bfo-2020\n"
        "    spine: true\n"
        "    latest: t\n"
        "    snapshots:\n"
        f"      t: {{ artifact: {BFO_ARTIFACT}, path: {root / 'bfo.zip'} }}\n",
        encoding="utf-8",
    )
    return root


def test_cli_export_writes_out_dir(cli_root: Path) -> None:
    from ledger._cli import main as ledger_main

    out_dir = cli_root / "out"
    rc = ledger_main(["export", "--root", str(cli_root), "--out", str(out_dir)])
    assert rc == 0
    text = (out_dir / "export.ttl").read_text(encoding="utf-8")
    assert "<ledger://public-thing> <ledger://predicate/colour> \"red\" ." in text.splitlines()


def test_cli_export_bad_plane_is_exit_2(cli_root: Path) -> None:
    from ledger._cli import main as ledger_main

    rc = ledger_main(["export", "--root", str(cli_root), "--plane", "nonsense"])
    assert rc == 2


def test_cli_export_gate_unverifiable_is_exit_0(cli_root: Path, monkeypatch) -> None:
    from ledger._cli import main as ledger_main

    monkeypatch.setenv("PATH", str(cli_root))  # no `robot` reachable
    monkeypatch.delenv("ATHENAEUM_REASONER", raising=False)
    rc = ledger_main(["export", "--root", str(cli_root), "--out", "-", "--gate"])
    assert rc == 0  # honestly-unverifiable is not a failure


def test_cli_export_gate_includes_registered_spine_payload(
    cli_root: Path, tmp_path: Path, monkeypatch, capsys,
) -> None:
    """End to end through the real CLI entrypoint: the registered bfo spine
    dataset (declared in `cli_root`'s athenaeum.yaml with a `path:` mirror
    override) gets extracted and handed to the reasoner as an extra
    `--input`, and the gate's detail carries no coverage caveat since the
    only registered spine dataset was successfully included."""
    import stat
    import textwrap

    from ledger._cli import main as ledger_main

    bin_dir = tmp_path / "bin"
    argv_log = tmp_path / "argv.log"
    bin_dir.mkdir()
    script = bin_dir / "robot"
    script.write_text(textwrap.dedent(f"""\
        #!/bin/sh
        printf '%s\\n' "$@" > "{argv_log}"
        exit 0
    """), encoding="utf-8")
    script.chmod(script.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("PATH", str(bin_dir))
    monkeypatch.delenv("ATHENAEUM_REASONER", raising=False)

    rc = ledger_main(["export", "--root", str(cli_root), "--out", "-", "--gate"])
    assert rc == 0
    err = capsys.readouterr().err
    assert "conformance gate: passed" in err
    assert "[spine" not in err  # full coverage — no caveat
    logged = argv_log.read_text(encoding="utf-8")
    assert "bfo-core.owl" in logged


# ---------------------------------------------------------------- gate input


def test_gate_hands_reasoner_owl_consumable_projection(ledger, tmp_path: Path) -> None:
    """OWLAPI/RDF4J cannot parse RDF 1.2's `<<( )>>` triple terms — the gate
    feeds the reasoner a projection with the `rdf:reifies` statements
    dropped (reifier annotation triples kept), while the full 1.2 text
    stays the export contract, written alongside for the record."""
    import sys

    from ledger.export import run_conformance_gate

    text, _ = _export(ledger)
    assert "<<(" in text  # the 1.2 export itself keeps its triple terms
    checker = tmp_path / "checker.py"
    checker.write_text(
        "import sys\n"
        "text = open(sys.argv[1], encoding='utf-8').read()\n"
        "sys.exit(2 if '<<(' in text else 0)\n",
        encoding="utf-8",
    )
    result = run_conformance_gate(
        text, work_dir=tmp_path / "gate",
        reasoner_cmd=f"{sys.executable} {checker} {{export}} {{output}}",
    )
    assert result.status == "passed"
    full = (tmp_path / "gate" / "export.ttl").read_text(encoding="utf-8")
    assert "<<(" in full
    projected = (tmp_path / "gate" / "export-reasoner.ttl").read_text(encoding="utf-8")
    assert "<<(" not in projected
    assert "#reifies>" not in projected
    # the reifier IRIs' plain annotation triples survive the narrowing
    assert f"<{PROV}wasQuotedFrom>" in projected
    assert "<ledger://meta/status>" in projected


def test_gate_failure_detail_filters_jvm_noise(ledger, tmp_path: Path) -> None:
    """robot's caffeine dep triggers the JDK sun.misc.Unsafe warning block on
    stderr ahead of anything useful — a failed gate's detail drops it so the
    real error leads."""
    import sys

    from ledger.export import run_conformance_gate

    text, _ = _export(ledger)
    noisy = tmp_path / "noisy.py"
    noisy.write_text(
        "import sys\n"
        "w = sys.stderr.write\n"
        "w('WARNING: A terminally deprecated method in sun.misc.Unsafe "
        "has been called\\n')\n"
        "w('WARNING: sun.misc.Unsafe::allocateMemory has been called by "
        "com.github.benmanes.caffeine.base.UnsafeAccess\\n')\n"
        "w('WARNING: Please consider reporting this to the maintainers of "
        "class com.github.benmanes.caffeine.base.UnsafeAccess\\n')\n"
        "w('WARNING: sun.misc.Unsafe::allocateMemory will be removed in a "
        "future release\\n')\n"
        "w('INVALID ONTOLOGY FILE ERROR: something real\\n')\n"
        "sys.exit(1)\n",
        encoding="utf-8",
    )
    result = run_conformance_gate(
        text, work_dir=tmp_path / "gate",
        reasoner_cmd=f"{sys.executable} {noisy} {{export}} {{output}}",
    )
    assert result.status == "failed"
    assert result.detail.startswith("INVALID ONTOLOGY FILE ERROR")
    assert "sun.misc.Unsafe" not in result.detail
