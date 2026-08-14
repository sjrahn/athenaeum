"""The ledger validation core: structure, graph, epistemics, evidence,
sensitivity, schemas, invariants, views (spec/ledger.md §13.1)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ath._cli import main as ath_main
from ledger._cli import main as ledger_main
from ledger.check import run_check
from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.model import canonical_claim_state, ensure_source, intervals_overlap, period_interval

H_PUB = "a" * 64      # resolves in the public corpus
H_PRIV = "b" * 64     # resolves only in the private corpus
H_BOTH = "c" * 64     # resolves in both → public evidence
H_PUB2 = "d" * 64     # second public record
H_NO_STATUS = "e" * 64  # public, no frontmatter `status` key (post-3.1-sweep world)
H_GONE = "f" * 64     # resolves nowhere

OPENQ_SKELETON = (
    "# Open questions\n\n<!--worklist:begin-->\n<!--worklist:end-->\n\n## Curated\n"
)


def _record(corpus_root: Path, h: str, status: str | None = "normalized") -> None:
    """`status` is decorative test frontmatter, not read by any production
    code (the corpus `status` field is retired, §4.1) — pass None to model
    the post-sweep record shape that carries no status key at all."""
    p = corpus_root / "records" / h[:2] / f"{h}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    status_line = f"status: {status}\n" if status is not None else ""
    p.write_text(f"---\nid: {h}\ntitle: t\n{status_line}---\n\nbody\n", encoding="utf-8")


@pytest.fixture()
def system(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "athenaeum.yaml").write_text(
        "org: https://example.test/org\n"
        "corpora:\n"
        "  corpus:\n"
        "    visibility: public\n"
        "  corpus-private:\n"
        "    visibility: private\n"
        "ledger:\n"
        "  ledger:\n"
        "references:\n"
        "  wikipedia:\n"
        "    description: test mirror\n"
        "    mirror: /mirrors/wp.zim\n"
        "    snapshot: '2026-06'\n"
    )
    pub = root / "corpora" / "corpus"
    priv = root / "corpora" / "corpus-private"
    for h in (H_PUB, H_BOTH, H_PUB2):
        _record(pub, h)
    _record(pub, H_NO_STATUS, status=None)
    for h in (H_PRIV, H_BOTH):
        _record(priv, h)
    ledger = root / "ledger"
    (ledger / "facts").mkdir(parents=True)
    (ledger / "interpretations").mkdir()
    (ledger / "ledger.yaml").write_text(
        "name: ledger\ncorpora: [corpus, corpus-private]\n"
    )
    (ledger / "open-questions.md").write_text(OPENQ_SKELETON)
    return root


def _resolve_sources(obj: dict) -> dict:
    """Test-authoring sugar, mirroring pre-migration `uri` ergonomics: an
    evidence entry carrying `_record`/`_ref` (this suite's shorthand for "cite
    this hash/dataset-id") resolves through `ensure_source` into the fact's own
    `sources` table, deduplicating repeats within one fact exactly as
    production authoring would. An entry already carrying `source` (exercising
    the raw shape directly) or the retired `uri` key (exercising the
    migration-error path) passes through untouched. Mutates *obj* (and its
    nested claim dicts) in place, and returns it."""
    sources = obj.setdefault("sources", {})
    for c in obj.get("claims") or []:
        if not isinstance(c, dict):
            continue
        evs = c.get("evidence")
        if not isinstance(evs, list):
            continue
        for e in evs:
            if not isinstance(e, dict) or "source" in e or "uri" in e:
                continue
            record = e.pop("_record", None)
            ref = e.pop("_ref", None)
            if record is not None:
                e["source"] = ensure_source(obj, record=record)
            elif ref is not None:
                e["source"] = ensure_source(obj, ref=ref)
    if not sources:
        del obj["sources"]
    return obj


def _fact(root: Path, type_: str, obj: dict) -> Path:
    obj = _resolve_sources(dict(obj))
    p = root / "ledger" / "facts" / type_ / f"{obj['id']}.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def _interp(root: Path, obj: dict) -> Path:
    p = root / "ledger" / "interpretations" / f"{obj['id']}.json"
    p.write_text(json.dumps(obj, indent=2), encoding="utf-8")
    return p


def _lineage(root: Path, mapping: dict[str, str]) -> Path:
    """Write (merging into any existing rows) `facts/LINEAGE.json` (§4.1)."""
    p = root / "ledger" / "facts" / "LINEAGE.json"
    existing = json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}
    existing.update(mapping)
    p.write_text(json.dumps(existing, indent=1), encoding="utf-8")
    return p


def _join(root: Path) -> CorpusJoin:
    return CorpusJoin([
        RegisteredCorpus("corpus", root / "corpora" / "corpus", private=False),
        RegisteredCorpus("corpus-private", root / "corpora" / "corpus-private", private=True),
    ])


def _check(root: Path, **kw):
    return run_check(root / "ledger", _join(root), {"wikipedia"}, **kw)


def _regen(root: Path) -> None:
    assert ledger_main(["regen", "--root", str(root)]) == 0


def _claim(fact_id: str, short: str, **over) -> dict:
    c = {
        "id": f"{fact_id}:{short}",
        "predicate": short.replace("-", "_"),
        "value": "x",
        "status": "provisional",
        "asof": "2026-07-02",
        "evidence": [{"_record": H_PUB, "kind": "direct"}],
    }
    c.update(over)
    return c


# ------------------------------------------------------------------ happy path


def test_clean_ledger_is_green(system: Path) -> None:
    _fact(system, "artist", {
        "id": "gorguts", "type": "artist", "name": "Gorguts",
        "artifacts": [{"uri": f"corpus://{H_PUB}", "role": "documents"}],
        "claims": [_claim("gorguts", "formed", value="1989", period="1989",
                          evidence=[{"_record": H_PUB, "anchor": "el=2",
                                    "kind": "authoritative"}],
                          status="confirmed")],
    })
    _fact(system, "album", {"id": "obscura", "type": "album", "name": "Obscura",
                            "claims": [_claim("obscura", "released-by", predicate="released_by",
                                              object="gorguts", period="1998")]})
    _interp(system, {
        "id": "obscura-length", "kind": "hypothesis", "about": ["obscura"],
        "statement": "Obscura runs about an hour.", "confidence": "plausible",
        "reasoning": "listing shows 60:01", "based_on": [f"corpus://{H_PUB}?el=3"],
        "proposes": {"id": "obscura:length", "predicate": "length", "value": "60:01",
                     "evidence": [{"uri": f"corpus://{H_PUB}?el=3", "kind": "direct"}]},
        "needs": [{"action": "capture", "why": "a second listing to corroborate"}],
        "status": "open", "asof": "2026-07-02",
    })
    _regen(system)
    rep = _check(system)
    assert rep.errors == []
    assert rep.warnings == []
    assert rep.counts["facts"] == 2
    assert rep.counts["claims"] == 2
    assert rep.counts["private_claims"] == 0


# ------------------------------------------------------------------- structure


def test_structure_errors(system: Path) -> None:
    p = _fact(system, "artist", {"id": "wrong", "type": "artist", "name": "X"})
    p.rename(p.with_name("other.json"))
    _fact(system, "album", {"id": "mistyped", "type": "artist", "name": "Y"})
    _fact(system, "artist", {"id": "junk", "type": "artist", "name": "Z", "extra": 1})
    rep = _check(system)
    msgs = "\n".join(rep.errors)
    assert "!= filename stem" in msgs
    assert "!= directory" in msgs
    assert "unknown concept keys" in msgs


def test_id_namespace_shared_with_interpretations(system: Path) -> None:
    _fact(system, "artist", {"id": "dup", "type": "artist", "name": "X"})
    _interp(system, {"id": "dup", "kind": "assessment", "statement": "s",
                     "reasoning": "r", "based_on": [f"corpus://{H_PUB}"],
                     "status": "standing", "asof": "2026-07-02"})
    rep = _check(system)
    assert any("share one namespace" in e for e in rep.errors)


def test_concept_needs_name_and_stub_is_valid(system: Path) -> None:
    _fact(system, "artist", {"id": "nameless", "type": "artist"})
    _fact(system, "artist", {"id": "stub-ok", "type": "artist", "name": "Stub"})
    rep = _check(system)
    assert any("no name" in e for e in rep.errors)
    assert not any("stub-ok" in e for e in rep.errors)


# ------------------------------------------------------------------- evidence


def test_evidence_source_discipline(system: Path) -> None:
    """The sources-table amendment's error surface: a resolving `record`/`ref`
    target, a bad hash shape, an unregistered `ref` dataset, both/neither of
    record|ref, a missing `source`, a dangling `source`, the retired inline
    `uri` field, and a leading `?` on `anchor`."""
    sources = {
        "s1": {"record": H_GONE},
        "s2": {"record": "not-a-hash"},
        "s3": {"ref": f"musicbrainz/{'1' * 8}"},
        "s4": {"ref": "wikipedia/Gorguts"},
        "s5": {"record": H_PUB, "ref": "wikipedia/x"},
    }
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "sources": sources,
        "claims": [
            _claim("x", "a", evidence=[{"source": "s1", "kind": "direct"}]),
            _claim("x", "b", evidence=[{"source": "s2", "kind": "direct"}]),
            _claim("x", "c", evidence=[{"source": "s3", "kind": "authoritative"}]),
            _claim("x", "d", evidence=[{"source": "s4", "kind": "direct"}]),
            _claim("x", "e", evidence=[{"source": "s5", "kind": "direct"}]),
            _claim("x", "f", evidence=[{"kind": "direct"}]),
            _claim("x", "g", evidence=[{"source": "ghost", "kind": "direct"}]),
            _claim("x", "h", evidence=[{"uri": f"corpus://{H_PUB}", "kind": "direct"}]),
            _claim("x", "i", evidence=[{"source": "s4", "anchor": "?el=2", "kind": "direct"}]),
        ],
    })
    rep = _check(system)
    msgs = "\n".join(rep.errors)
    assert "resolves in no registered corpus" in msgs           # s1 (H_GONE)
    assert "not a full 64-hex blake3 hash" in msgs               # s2
    assert "'musicbrainz' is not registered" in msgs             # s3
    assert "exactly one of" in msgs                              # s5
    assert "evidence entry has no source" in msgs                # f
    assert "does not resolve in this fact's sources" in msgs     # g (ghost)
    assert "retired inline `uri` field" in msgs                  # h
    assert "must not carry a leading '?'" in msgs                # i


def test_sources_duplicate_target(system: Path) -> None:
    sources = {"s1": {"record": H_PUB}, "s2": {"record": H_PUB}}
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "sources": sources,
        "claims": [_claim("x", "a", evidence=[{"source": "s1", "kind": "direct"}])],
    })
    rep = _check(system)
    assert any("duplicate source for record" in e for e in rep.errors)


def test_sources_unused_warns(system: Path) -> None:
    sources = {"s1": {"record": H_PUB}}
    _fact(system, "artist", {"id": "x", "type": "artist", "name": "X", "sources": sources})
    rep = _check(system)
    assert any("not referenced by any evidence" in w for w in rep.warnings)


def test_source_resolution_checked_once_not_per_evidence(system: Path) -> None:
    """Resolution checks fire ONCE per sources entry — two claims sharing one
    source must not double the message."""
    sources = {"s1": {"record": H_GONE}}
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "sources": sources,
        "claims": [
            _claim("x", "a", evidence=[{"source": "s1", "kind": "direct"}]),
            _claim("x", "b", evidence=[{"source": "s1", "kind": "direct"}]),
        ],
    })
    rep = _check(system)
    assert sum("resolves in no registered corpus" in e for e in rep.errors) == 1


def test_no_status_field_checks_clean(system: Path) -> None:
    """1.1 (§6.3, §13.1): citability keys to verifiable surfaces, never to a
    stored status flag — the 1.0 cited-records-are-`normalized` check
    retires with the corpus `status` field. A record carrying no frontmatter
    `status` key at all (the post-3.1-sweep shape, `spec/corpus.md` §4.1)
    checks clean: no warning, no crash."""
    sources = {"s1": {"record": H_NO_STATUS}}
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "sources": sources,
        "claims": [_claim("x", "a", evidence=[{"source": "s1", "kind": "direct"}])],
    })
    rep = _check(system)
    assert not rep.errors
    assert not any("status" in w for w in rep.warnings)


def test_no_corpus_skips_resolution(system: Path) -> None:
    sources = {"s1": {"record": H_GONE}}
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "sources": sources,
        "claims": [_claim("x", "a", evidence=[{"source": "s1", "kind": "direct"}])],
    })
    rep = _check(system, no_corpus=True)
    assert not any("resolves in no registered corpus" in e for e in rep.errors)
    assert any("--no-corpus" in n for n in rep.notes)


# ----------------------------------------------------------------- sensitivity


def test_sensitivity_is_derived(system: Path) -> None:
    _fact(system, "person", {
        "id": "p", "type": "person", "name": "P",
        "claims": [
            _claim("p", "a", evidence=[{"_record": H_PRIV, "kind": "direct"}]),
            _claim("p", "b", evidence=[{"_record": H_BOTH, "kind": "direct"}]),
        ],
    })
    _fact(system, "place", {
        "id": "home", "type": "place", "name": "Home", "sensitivity": "private",
        "claims": [_claim("home", "a")],
    })
    rep = _check(system)
    # H_PRIV resolves only privately → claim a is private-backed; H_BOTH is public.
    assert rep.counts["private_claims"] == 1
    # p has a public claim → file public; home asserts private → file private.
    assert rep.counts["private_files"] == 1


def test_sensitivity_rekeys_to_record_tenancy(system: Path) -> None:
    """§6.4 *(1.9)*: sensitivity derives from record TENANCY, not corpus
    membership. An origin overlay declaring `tenancy: public` makes a
    private-corpus record public evidence; a promoted member inherits through
    its `corpus://` lineage; a `tenancy: private` declaration in a public
    corpus is an answer, not the floor; and undeclared records keep the
    manifest-visibility fallback (every other test in this suite rides it)."""
    import frontmatter

    from corpus import paths, records

    priv = system / "corpora" / "corpus-private"
    pub = system / "corpora" / "corpus"
    (priv / "schema" / "origin" / "web").mkdir(parents=True)
    (priv / "schema" / "origin" / "web" / "openhost.yaml").write_text(
        "tenancy: public\n", encoding="utf-8")
    (pub / "schema" / "origin").mkdir(parents=True)
    (pub / "schema" / "origin" / "sealed-export.yaml").write_text(
        "tenancy: private\n", encoding="utf-8")

    declared, member, sealed = "1" * 64, "2" * 64, "3" * 64

    def _mk(root: Path, h: str, *, uri: str, schema_id: str | None,
            touch: str = "corpus.ingest@0.1.0") -> None:
        post = frontmatter.Post(
            content="", **records.stub_frontmatter(record_id=h, touch_id=touch))
        records.set_artifact_block(post, mime="text/plain", fields={})
        records.append_origin_block(
            post, uri=uri, snapshot="2026-01-01T00:00:00Z", schema_id=schema_id)
        records.dump(post, paths.record_path(root, h))

    _mk(priv, declared, uri="https://openhost/x", schema_id="openhost")
    _mk(priv, member, uri=f"corpus://{declared}?path=a.txt", schema_id=None,
        touch="corpus.promote@0.1.0")
    _mk(pub, sealed, uri="file:///export/blob", schema_id="sealed-export")

    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "claims": [
            _claim("x", "a", evidence=[{"_record": declared, "kind": "direct"}]),
            _claim("x", "b", evidence=[{"_record": member, "kind": "direct"}]),
            _claim("x", "c", evidence=[{"_record": H_PRIV, "kind": "direct"}]),
            _claim("x", "d", evidence=[{"_record": sealed, "kind": "direct"}]),
        ],
    })
    rep = _check(system)
    # `declared` and `member` are public despite living only in corpus-private;
    # H_PRIV keeps the private floor; `sealed` is private despite the public corpus
    assert rep.counts["private_claims"] == 2


def test_asserted_sensitivity_is_upward_only(system: Path) -> None:
    _fact(system, "person", {
        "id": "p", "type": "person", "name": "P", "sensitivity": "public",
        "claims": [_claim("p", "a", sensitivity="public")],
    })
    rep = _check(system)
    assert sum("upward only" in e for e in rep.errors) == 2


# ------------------------------------------------------------------ epistemics


def test_authentication_bar(system: Path) -> None:
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "claims": [
            _claim("x", "weak", status="confirmed",
                   evidence=[{"_record": H_PUB, "kind": "direct"}]),
            _claim("x", "strong", status="confirmed",
                   evidence=[{"_record": H_PUB, "kind": "direct"},
                             {"_record": H_PUB2, "kind": "direct"}]),
        ],
    })
    rep = _check(system)
    assert sum("authentication bar" in e for e in rep.errors) == 1


def _html_record(corpus_root: Path, h: str, *, formed: bool) -> None:
    """A `text/html` record — `segments`-citation-surface (corpus §7.1's built-in
    table). Formless it is a DEFERRED surface (§5.4, 1.8); with one persisted
    segment it is verifiable and counts toward the bar again."""
    p = corpus_root / "records" / h[:2] / f"{h}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    seg = "<!--segment text el=1\n-->\nhello\n" if formed else ""
    p.write_text(f"---\nid: {h}\n---\n\n<!--artifact text/html\n-->\n\n{seg}",
                 encoding="utf-8")


def test_authentication_bar_excludes_deferred_surfaces(system: Path) -> None:
    """*(1.8, §5.4)* The bar counts only verifiable-surface evidence. Deferred
    surfaces (segment-less `segments`-surface records) carry a claim on every
    lower rung, but never to `confirmed` — not as the authoritative artifact,
    not toward independence — and the error names the actual defect. A formed
    record of the same mime counts normally, and a mixed claim whose countable
    evidence still meets the bar passes."""
    d1, d2, formed = "9" * 64, "8" * 64, "7" * 64
    pub = system / "corpora" / "corpus"
    _html_record(pub, d1, formed=False)
    _html_record(pub, d2, formed=False)
    _html_record(pub, formed, formed=True)
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "claims": [
            # two independent records — but both deferred: fails, with the 1.8 cause
            _claim("x", "both-deferred", status="confirmed",
                   evidence=[{"_record": d1, "kind": "direct"},
                             {"_record": d2, "kind": "direct"}]),
            # authoritative — but deferred: authority can't ride an unformed surface
            _claim("x", "auth-deferred", status="confirmed",
                   evidence=[{"_record": d1, "kind": "authoritative"}]),
            # countable evidence meets the bar; a deferred rider changes nothing
            _claim("x", "mixed-ok", status="confirmed",
                   evidence=[{"_record": H_PUB, "kind": "authoritative"},
                             {"_record": d1, "kind": "direct"}]),
            # a FORMED record of the same mime is verifiable-surface evidence
            _claim("x", "formed-ok", status="confirmed",
                   evidence=[{"_record": formed, "kind": "authoritative"}]),
            # below the bar, deferred evidence is simply admissible
            _claim("x", "provisional-ok", status="provisional",
                   evidence=[{"_record": d1, "kind": "direct"}]),
        ],
    })
    rep = _check(system)
    bar_errors = [e for e in rep.errors if "authentication bar" in e]
    assert len(bar_errors) == 2
    assert all("deferred surfaces" in e for e in bar_errors)
    assert any("x:both-deferred" in e for e in bar_errors)
    assert any("x:auth-deferred" in e for e in bar_errors)


def test_reported_requires_attribution(system: Path) -> None:
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "claims": [_claim("x", "opinion", status="reported")],
    })
    rep = _check(system)
    assert any("attribution" in e for e in rep.errors)


def test_harvest_provenance_capped_provisional(system: Path) -> None:
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "claims": [_claim("x", "a", provenance="auto", status="confirmed",
                          evidence=[{"_record": H_PUB, "kind": "authoritative"}])],
    })
    rep = _check(system)
    assert any("capped at provisional" in e for e in rep.errors)


def test_challenge_pin_lifecycle(system: Path) -> None:
    claim = _claim("x", "wrong", status="disputed")
    obj = _resolve_sources({"id": "x", "type": "artist", "name": "X", "claims": [claim]})
    _fact(system, "artist", obj)
    interp = {
        "id": "x-wrong-challenge", "kind": "correction", "about": ["x"],
        "statement": "claim x:wrong misreads the source.",
        "reasoning": "the quote is about a different model year",
        "based_on": [f"corpus://{H_PUB}"],
        "challenges": {"claim": "x:wrong",
                       "state": canonical_claim_state(claim, obj.get("sources") or {})},
        "status": "standing", "asof": "2026-07-02",
    }
    _interp(system, interp)
    rep = _check(system)
    assert not any("re-review" in w for w in rep.warnings)
    assert not any("disputed claim has no standing correction" in e for e in rep.errors)
    # edit the claim's content → the pin flags re-review
    claim["value"] = "y"
    _fact(system, "artist", obj)
    rep = _check(system)
    assert any("needs re-review" in w for w in rep.warnings)


def test_challenge_pin_survives_source_key_rename(system: Path) -> None:
    """The pin canonicalizes through the DERIVED uri (§7.3 amendment): a
    source-key rename over the SAME record must not move it, but a genuine
    record swap under the same key must."""
    claim = _claim("x", "wrong", status="disputed")
    obj = _resolve_sources({"id": "x", "type": "artist", "name": "X", "claims": [claim]})
    _fact(system, "artist", obj)
    state = canonical_claim_state(claim, obj["sources"])
    _interp(system, {
        "id": "x-wrong-challenge", "kind": "correction", "about": ["x"],
        "statement": "claim x:wrong misreads the source.",
        "reasoning": "r", "based_on": [f"corpus://{H_PUB}"],
        "challenges": {"claim": "x:wrong", "state": state},
        "status": "standing", "asof": "2026-07-02",
    })

    # rename the source key (same underlying record) — the derived uri, and
    # hence the pin, must not move
    old_key = next(iter(obj["sources"]))
    entry = obj["sources"].pop(old_key)
    obj["sources"]["renamed"] = entry
    claim["evidence"][0]["source"] = "renamed"
    _fact(system, "artist", obj)
    rep = _check(system)
    assert not any("re-review" in w for w in rep.warnings)

    # a genuine record swap under the SAME key must still flag re-review
    obj["sources"]["renamed"] = {"record": H_PUB2}
    _fact(system, "artist", obj)
    rep = _check(system)
    assert any("needs re-review" in w for w in rep.warnings)


def test_proposes_evidence_shape(system: Path) -> None:
    """`proposes` predates the fact it targets, so its evidence stays inline-
    `uri`-shaped pre-promotion: a `source`/`anchor` key is an error (there is
    no sources table to reference yet), as is an unknown key or a malformed/
    unregistered `uri` — the same grammar claim evidence used to carry."""
    _fact(system, "artist", {"id": "x", "type": "artist", "name": "X"})
    _interp(system, {
        "id": "x-guess", "kind": "hypothesis", "about": ["x"],
        "statement": "s", "confidence": "plausible", "reasoning": "r",
        "based_on": [f"corpus://{H_PUB}"],
        "proposes": {
            "id": "x:guess", "predicate": "guess", "value": "v",
            "evidence": [
                {"source": "s1", "kind": "direct"},
                {"uri": f"corpus://{H_PUB}", "kind": "direct", "bogus": True},
                {"uri": "not-a-citation", "kind": "direct"},
                {"uri": f"ref://musicbrainz/{'1' * 8}", "kind": "direct"},
            ],
        },
        "status": "open", "asof": "2026-07-02",
    })
    rep = _check(system)
    msgs = "\n".join(rep.errors)
    assert "sources-table `source`/`anchor` key" in msgs
    assert "proposes evidence unknown keys ['bogus']" in msgs
    assert "proposes evidence uri 'not-a-citation' is not a corpus:// or ref:// citation" in msgs
    assert "proposes evidence ref:// dataset 'musicbrainz' is not registered" in msgs


def test_disputed_requires_standing_correction(system: Path) -> None:
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "claims": [_claim("x", "a", status="disputed")],
    })
    rep = _check(system)
    assert any("no standing correction" in e for e in rep.errors)


# ----------------------------------------------------------------------- graph


def test_lineage_resolves_one_hop(system: Path) -> None:
    _fact(system, "artist", {"id": "survivor", "type": "artist", "name": "S"})
    _lineage(system, {"old": "survivor", "older": "old"})
    _fact(system, "album", {
        "id": "a", "type": "album", "name": "A",
        "claims": [_claim("a", "by", predicate="released_by", object="old")],
    })
    rep = _check(system)
    # object through one lineage hop is fine; a lineage chain is not
    assert not any("dangling object" in e for e in rep.errors)
    assert any("one-hop rule" in e for e in rep.errors)


def test_legacy_redirect_shape_is_a_check_error(system: Path) -> None:
    """A fact file still carrying the retired `merged_into` tombstone shape
    (pre-1.7) is a check ERROR — lineage now lives only in
    facts/LINEAGE.json (§4.1)."""
    _fact(system, "artist", {"id": "survivor", "type": "artist", "name": "S"})
    _fact(system, "artist", {"id": "old", "type": "artist", "merged_into": "survivor"})
    rep = _check(system)
    assert any("fold into facts/LINEAGE.json" in e for e in rep.errors)


def test_lineage_key_colliding_with_living_id(system: Path) -> None:
    _fact(system, "artist", {"id": "survivor", "type": "artist", "name": "S"})
    _fact(system, "artist", {"id": "old", "type": "artist", "name": "Old"})
    _lineage(system, {"old": "survivor"})
    rep = _check(system)
    assert any("lineage key 'old' collides with a living id" in e for e in rep.errors)


def test_lineage_dangling_value(system: Path) -> None:
    _fact(system, "artist", {"id": "survivor", "type": "artist", "name": "S"})
    _lineage(system, {"old": "ghost"})
    rep = _check(system)
    assert any("'ghost' does not exist" in e for e in rep.errors)


def test_lineage_json_is_not_a_stray_fact_file(system: Path) -> None:
    """facts/LINEAGE.json lives directly under facts/ by design (§4.1) — the
    stray-fact-file check (fact files must live under facts/{type}/) must not
    flag it."""
    _fact(system, "artist", {"id": "survivor", "type": "artist", "name": "S"})
    _lineage(system, {"old": "survivor"})
    rep = _check(system)
    assert not any("LINEAGE.json" in e and "not facts/" in e for e in rep.errors)


def test_dangling_references(system: Path) -> None:
    _fact(system, "album", {
        "id": "a", "type": "album", "name": "A",
        "claims": [_claim("a", "by", predicate="released_by", object="ghost",
                          value="by [[nobody]]")],
    })
    _fact(system, "event", {"id": "e", "type": "event", "subject": "ghost",
                            "participants": ["ghost2"], "title": "E",
                            "claims": [_claim("e", "happened")]})
    rep = _check(system)
    msgs = "\n".join(rep.errors)
    assert "dangling object 'ghost'" in msgs
    assert "[[nobody]]" in msgs
    assert "dangling subject" in msgs
    assert "dangling participant" in msgs


# --------------------------------------------------------------------- schemas


def test_schema_conformance(system: Path) -> None:
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "song.yaml").write_text(
        "type: song\ndescription: a song\n"
        "fields:\n  appears_on: { target: album }\n  length: {}\n"
        "roster_roles: [tablature-of, performance-of]\n"
    )
    _fact(system, "artist", {"id": "band", "type": "artist", "name": "B"})
    _fact(system, "song", {
        "id": "s", "type": "song", "name": "S",
        "artifacts": [{"uri": f"corpus://{H_PUB}", "role": "bucket-things"}],
        "claims": [_claim("s", "appears-on", predicate="appears_on", object="band")],
    })
    rep = _check(system)
    msgs = "\n".join(rep.errors)
    assert "targets 'album'" in msgs
    assert "not among the 'song' schema's roster_roles" in msgs
    # a stub song with no claims is frontier, not an error
    _fact(system, "song", {"id": "s2", "type": "song", "name": "S2"})
    rep = _check(system)
    assert not any("s2" in e for e in rep.errors)


def test_schema_union_target(system: Path) -> None:
    """`target` may list admissible types (spec §4.4) — any listed type passes,
    anything else is mis-shape."""
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "song.yaml").write_text(
        "type: song\ndescription: a song\n"
        "fields:\n  tribute_to: { target: [artist, song] }\n"
    )
    _fact(system, "artist", {"id": "band", "type": "artist", "name": "B"})
    _fact(system, "album", {"id": "lp", "type": "album", "name": "LP"})
    _fact(system, "song", {
        "id": "ok", "type": "song", "name": "OK",
        "claims": [_claim("ok", "tribute", predicate="tribute_to", object="band")],
    })
    rep = _check(system)
    assert not any("tribute" in e for e in rep.errors)
    _fact(system, "song", {
        "id": "bad", "type": "song", "name": "Bad",
        "claims": [_claim("bad", "tribute", predicate="tribute_to", object="lp")],
    })
    rep = _check(system)
    assert any("targets ['artist', 'song']" in e and "'album'" in e
               for e in rep.errors)
    # a malformed target shape is a schema error
    (system / "ledger" / "schemas" / "song.yaml").write_text(
        "type: song\ndescription: a song\nfields:\n  tribute_to: { target: 7 }\n"
    )
    rep = _check(system)
    assert any("target must be a type or a list" in e for e in rep.errors)


def test_frontier_aggregates_per_field(system: Path) -> None:
    """An `expected: true` field most facts lack renders as ONE aggregated
    worklist line, not a per-fact flood; an unmarked field is admissible
    vocabulary and never frontier."""
    from ledger.views import render_worklist
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "song.yaml").write_text(
        "type: song\ndescription: a song\n"
        "fields:\n  appears_on: { target: album, expected: true }\n"
        "  covered_by: { target: artist }\n"
    )
    for i in range(7):
        _fact(system, "song", {
            "id": f"song-{i}", "type": "song", "name": f"S{i}",
            "claims": [_claim(f"song-{i}", "length", predicate="length",
                              value="3:00")],
        })
    from ledger.model import load_json_dir
    facts, _ = load_json_dir(system / "ledger", "facts/*/*.json")
    from ledger.schemas import load_schemas
    schemas, _ = load_schemas(system / "ledger")
    block = render_worklist(facts, {}, schemas)
    assert "`song.appears_on` not yet attested on 7 facts" in block
    assert block.count("appears_on") == 1  # one line, not seven
    assert "covered_by" not in block  # admissible, not owed — no frontier


def test_edge_schema_participants(system: Path) -> None:
    """An edge schema's `participants` is positional: count and per-slot type
    are validated; a type mismatch or count divergence is mis-shape (§4.4)."""
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "relationship.yaml").write_text(
        "type: relationship\ndescription: a person-person tie\n"
        "participants: [person, person]\n"
        "fields:\n  kind: { values: [friend, sibling] }\n"
    )
    for pid in ("a", "b"):
        _fact(system, "person", {"id": pid, "type": "person", "name": pid.upper(),
                                 "claims": [_claim(pid, "email", predicate="email")]})
    _fact(system, "organization", {"id": "org", "type": "organization", "name": "O",
                                   "claims": [_claim("org", "d", predicate="description")]})
    _fact(system, "relationship", {
        "id": "a--b", "type": "relationship", "participants": ["a", "b"],
        "claims": [_claim("a--b", "kind", predicate="kind", value="friend")],
    })
    _fact(system, "relationship", {
        "id": "a--org", "type": "relationship", "participants": ["a", "org"],
        "claims": [_claim("a--org", "kind", predicate="kind", value="friend")],
    })
    _fact(system, "relationship", {
        "id": "solo", "type": "relationship", "participants": ["a"],
        "claims": [_claim("solo", "kind", predicate="kind", value="friend")],
    })
    rep = _check(system)
    msgs = "\n".join(rep.errors)
    assert not any("a--b.json" in e for e in rep.errors)
    assert "participants[1] 'org' is a 'organization', declared 'person'" in msgs
    assert "declares participants ['person', 'person'], found 1" in msgs


def test_schema_values_and_participant_flag(system: Path) -> None:
    """A field's `values` is an enumerated value vocabulary; `participant: true`
    pins a directed kind's object to the edge's own participants (§4.4)."""
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "relationship.yaml").write_text(
        "type: relationship\ndescription: a person-person tie\n"
        "fields:\n"
        "  kind: { values: [friend, father-of], target: person, participant: true }\n"
    )
    for pid in ("a", "b", "c"):
        _fact(system, "person", {"id": pid, "type": "person", "name": pid.upper(),
                                 "claims": [_claim(pid, "email", predicate="email")]})
    _fact(system, "relationship", {
        "id": "a--b", "type": "relationship", "participants": ["a", "b"],
        "claims": [_claim("a--b", "kind", predicate="kind", value="father-of",
                          object="b")],
    })
    _fact(system, "relationship", {
        "id": "b--c", "type": "relationship", "participants": ["b", "c"],
        "claims": [
            _claim("b--c", "kind", predicate="kind", value="nemesis"),
            _claim("b--c", "kind-2", predicate="kind", value="father-of", object="a"),
        ],
    })
    rep = _check(system)
    msgs = "\n".join(rep.errors)
    assert not any("a--b.json" in e for e in rep.errors)
    assert "value 'nemesis' not among declared values" in msgs
    assert "object must be one of the edge's participants ['b', 'c'] (got 'a')" in msgs


def test_expectations_frontier(system: Path) -> None:
    """Conditional owed-ness (§4.4): an `expectations` entry owes its fields
    only on the facts its `when` selects — and never on the `with:` fact
    itself. The reserved name `period` owes the fact's own timebox, which
    puts edges on the frontier too."""
    from ledger.model import load_json_dir
    from ledger.schemas import load_schemas
    from ledger.views import render_worklist
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "person.yaml").write_text(
        "type: person\ndescription: a person\n"
        "fields:\n  date_of_birth: {}\n"
        "expectations:\n"
        "  - description: family birthdays are chase-worthy\n"
        "    when: { relationship: { kind: [sibling], with: steven } }\n"
        "    expect: [date_of_birth]\n"
    )
    (system / "ledger" / "schemas" / "employment.yaml").write_text(
        "type: employment\ndescription: an employment episode\n"
        "expectations:\n"
        "  - description: every episode is timeboxed\n"
        "    expect: [period]\n"
    )
    for pid in ("steven", "kat", "stranger"):
        _fact(system, "person", {"id": pid, "type": "person", "name": pid.title(),
                                 "claims": [_claim(pid, "email", predicate="email")]})
    _fact(system, "organization", {"id": "acme", "type": "organization", "name": "Acme",
                                   "claims": [_claim("acme", "d", predicate="description")]})
    _fact(system, "relationship", {
        "id": "steven--kat", "type": "relationship", "participants": ["steven", "kat"],
        "claims": [_claim("steven--kat", "kind", predicate="kind", value="sibling")],
    })
    _fact(system, "employment", {
        "id": "steven--acme", "type": "employment", "participants": ["steven", "acme"],
        "claims": [_claim("steven--acme", "role", predicate="employed_by",
                          object="acme")],
    })
    facts, _ = load_json_dir(system / "ledger", "facts/*/*.json")
    schemas, _ = load_schemas(system / "ledger")
    block = render_worklist(facts, {}, schemas)
    assert ("`person.date_of_birth` — family birthdays are chase-worthy — "
            "not yet attested: `kat`") in block
    # steven (named by with:) and stranger (not family) are never owed
    assert "`steven`" not in block
    assert "`stranger`" not in block
    # the employment edge has no period → frontier via the reserved name
    assert "`employment.period`" in block and "`steven--acme`" in block
    # attesting the owed field clears the gap
    _fact(system, "person", {"id": "kat", "type": "person", "name": "Kat",
                             "claims": [_claim("kat", "dob", predicate="date_of_birth",
                                               value="1990-01-01")]})
    facts, _ = load_json_dir(system / "ledger", "facts/*/*.json")
    block = render_worklist(facts, {}, schemas)
    assert "date_of_birth" not in block


def test_timeboxed_fields_frontier(system: Path) -> None:
    """`timeboxed: true` (§4.4): every claim under the predicate owes a
    `period` — an episode without a timespan is half a fact. The gap is a
    chase on the frontier, never an error; `asof` alone does not satisfy it."""
    from ledger.model import load_json_dir
    from ledger.schemas import load_schemas
    from ledger.views import render_worklist
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "person.yaml").write_text(
        "type: person\ndescription: a person\n"
        "fields:\n  residence: { timeboxed: true }\n  interest: {}\n"
    )
    _fact(system, "person", {"id": "kat", "type": "person", "name": "Kat",
                             "claims": [
                                 _claim("kat", "res-a", predicate="residence"),
                                 _claim("kat", "res-b", predicate="residence",
                                        period="2020/2022"),
                                 _claim("kat", "hobby", predicate="interest"),
                             ]})
    facts, _ = load_json_dir(system / "ledger", "facts/*/*.json")
    schemas, errs = load_schemas(system / "ledger")
    assert not errs
    block = render_worklist(facts, {}, schemas)
    assert ("`person.residence` claims missing their timebox (`period`): "
            "`kat:res-a`") in block
    assert "kat:res-b" not in block       # a period satisfies the timebox
    assert "kat:hobby" not in block       # unmarked fields owe nothing
    # shape: timeboxed must be a bool
    (system / "ledger" / "schemas" / "person.yaml").write_text(
        "type: person\ndescription: a person\n"
        "fields:\n  residence: { timeboxed: sometimes }\n"
    )
    _, errs = load_schemas(system / "ledger")
    assert any("timeboxed must be a bool" in e for e in errs)


def test_concept_carries_own_period(system: Path) -> None:
    """A concept MAY carry a top-level `period` (§4.2): admitted (not an unknown
    key), format-warned like a claim period, and it satisfies a `period`
    expectation the way an edge's own timebox does."""
    from ledger.model import load_json_dir
    from ledger.schemas import load_schemas
    from ledger.views import render_worklist
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "event.yaml").write_text(
        "type: event\ndescription: an occurrence\n"
        "expectations:\n"
        "  - description: every event is timeboxed\n"
        "    expect: [period]\n"
    )
    _fact(system, "event", {
        "id": "fest", "type": "event", "name": "Fest",
        "period": "2026-07-08/2026-07-09",
        "claims": [_claim("fest", "kind", value="festival",
                          period="2026-07-08/2026-07-09")],
    })
    rep = _check(system)
    assert not any("unknown concept keys" in e for e in rep.errors)
    assert not any("odd period format" in w for w in rep.warnings)  # well-formed
    # the top-level timebox satisfies the `expect: [period]` frontier line
    facts, _ = load_json_dir(system / "ledger", "facts/*/*.json")
    schemas, _ = load_schemas(system / "ledger")
    assert "event.period" not in render_worklist(facts, {}, schemas)

    # an odd top-level period format warns, exactly like a claim period
    _fact(system, "event", {
        "id": "fest2", "type": "event", "name": "Fest2",
        "period": "July 2026",
        "claims": [_claim("fest2", "kind", value="festival")],
    })
    rep = _check(system)
    assert not any("unknown concept keys" in e for e in rep.errors)
    assert any("odd period format" in w and "fest2" in w for w in rep.warnings)


def test_schema_elements_and_entity_refs(system: Path) -> None:
    """Declared `elements` (§4.4) validate the objects inside a structured array
    claim value — enum `values` and typed `entity` `target`s — while undeclared
    keys, {"name"}/{"handle"} elements, and non-dict elements validate nothing.
    And, independent of any declaration, every {"entity": <id>} in a claim value
    MUST resolve (through the lineage map, §4.1) — the no-dangling rule extended
    to the roster shape."""
    from ledger.schemas import load_schemas
    (system / "ledger" / "schemas").mkdir()
    (system / "ledger" / "schemas" / "event.yaml").write_text(
        "type: event\ndescription: an occurrence\n"
        "fields:\n"
        "  attendance:\n"
        "    elements:\n"
        "      entity: { target: person }\n"
        "      role: { values: [worked, attended, performed] }\n"
        "  lineup:\n"
        "    elements:\n"
        "      entity: { target: organization }\n"
    )
    for pid in ("steven", "kat"):
        _fact(system, "person", {"id": pid, "type": "person", "name": pid.title(),
                                 "claims": [_claim(pid, "email", predicate="email")]})
    _lineage(system, {"renamed": "steven"})
    _fact(system, "organization", {"id": "acme", "type": "organization", "name": "Acme",
                                   "claims": [_claim("acme", "d", predicate="description")]})

    # clean: entity → person, role in vocab, undeclared `capacity` tolerated; a
    # renamed entity resolves through the lineage map; {"name"}/{"handle"}
    # and a bare-string element validate nothing; lineup entity → organization
    # with an undeclared free-text `role`.
    _fact(system, "event", {
        "id": "ok", "type": "event", "name": "OK", "period": "2026-07",
        "claims": [
            _claim("ok", "att", predicate="attendance", period="2026-07", value=[
                {"entity": "steven", "role": "worked", "capacity": "Volunteer Manager"},
                {"entity": "renamed", "role": "attended"},
                {"name": "Unminted Person"},
                {"handle": "+15551234"},
                "not-a-dict",
            ]),
            _claim("ok", "lineup", predicate="lineup", period="2026-07", value=[
                {"name": "Some Band"},
                {"entity": "acme", "role": "headliner"},
            ]),
        ]})
    rep = _check(system)
    assert not any("ok.json" in e for e in rep.errors)

    # role outside its vocabulary; entity a wrong type; entity dangling
    _fact(system, "event", {
        "id": "bad", "type": "event", "name": "Bad", "period": "2026-07",
        "claims": [_claim("bad", "att", predicate="attendance", period="2026-07", value=[
            {"entity": "steven", "role": "vibed"},
            {"entity": "acme", "role": "worked"},
            {"entity": "ghost", "role": "attended"},
        ])]})
    rep = _check(system)
    msgs = "\n".join(rep.errors)
    assert "element 'role' value 'vibed' not among declared values" in msgs
    assert "element 'entity' 'acme' is a 'organization', declared target 'person'" in msgs
    assert "dangling entity reference 'ghost' in claim value" in msgs
    # a wrong-type entity resolves, so it is NOT also reported as dangling
    assert "dangling entity reference 'acme'" not in msgs

    # a malformed element declaration is a schema error
    (system / "ledger" / "schemas" / "event.yaml").write_text(
        "type: event\ndescription: an occurrence\n"
        "fields:\n  attendance:\n    elements:\n      entity: { target: 7 }\n"
    )
    _, errs = load_schemas(system / "ledger")
    assert any("element 'entity' target must be a type or a list" in e for e in errs)


# ------------------------------------------------------------------ invariants


def test_invariants(system: Path) -> None:
    inv_dir = system / "ledger" / "invariants"
    inv_dir.mkdir()
    (inv_dir / "one-platform.yaml").write_text(
        "id: one-platform\ndescription: a vehicle has one platform\n"
        "applies_to: { type: vehicle, predicate: platform }\n"
        "constraint: unique\nseverity: error\n"
    )
    (inv_dir / "residence-no-overlap.yaml").write_text(
        "id: residence-no-overlap\ndescription: one residence at a time\n"
        "applies_to: { type: person, predicate: residence }\n"
        "constraint: temporal-no-overlap\nseverity: warning\n"
    )
    _fact(system, "vehicle", {
        "id": "v", "type": "vehicle", "name": "V",
        "claims": [_claim("v", "platform-a", predicate="platform"),
                   _claim("v", "platform-b", predicate="platform")],
    })
    _fact(system, "person", {
        "id": "p", "type": "person", "name": "P",
        "claims": [_claim("p", "res-1", predicate="residence", period="2019/2021"),
                   _claim("p", "res-2", predicate="residence", period="2020/..")],
    })
    rep = _check(system)
    assert any("one-platform" in e and "2 matching claims" in e for e in rep.errors)
    assert any("residence-no-overlap" in w and "overlapping" in w for w in rep.warnings)


def test_period_calculus() -> None:
    assert period_interval("2019") == ((2019, 1, 1), (2019, 12, 31))
    assert period_interval("~2020-03") == ((2020, 3, 1), (2020, 3, 31))
    assert period_interval("2019/..")[1] == (9999, 12, 31)
    a = period_interval("2019/2021")
    b = period_interval("2021-06")
    c = period_interval("2022")
    assert intervals_overlap(a, b)
    assert not intervals_overlap(a, c)


# ----------------------------------------------------------------------- views


def test_views_regen_and_staleness(system: Path) -> None:
    _fact(system, "artist", {
        "id": "x", "type": "artist", "name": "X",
        "artifacts": [{"uri": f"corpus://{H_PUB}", "role": "documents"}],
        "claims": [_claim("x", "formed", qualifiers={"attribution": "him"},
                          status="reported")],
    })
    rep = _check(system)
    assert any("VOCAB.md" in w and "missing" in w for w in rep.warnings)
    _regen(system)
    rep = _check(system)
    assert not any("VOCAB.md" in w for w in rep.warnings)
    vocab = (system / "ledger" / "facts" / "VOCAB.md").read_text()
    assert "| `artist` | 1 |" in vocab
    assert "| `formed` | 1 |" in vocab
    assert "| `documents` | 1 |" in vocab
    assert "| `attribution` | 1 |" in vocab
    # a new fact makes the views stale
    _fact(system, "artist", {"id": "y", "type": "artist", "name": "Y"})
    rep = _check(system)
    assert any("VOCAB.md" in w and "stale" in w for w in rep.warnings)
    assert any("open-questions.md" in w for w in rep.warnings)  # stub frontier appeared


def test_retired_vocabulary_is_rejected(system: Path) -> None:
    _fact(system, "artist", {"id": "x", "type": "artist", "name": "X",
                             "claims": [_claim("x", "shoe-size", predicate="shoe_size")]})
    _regen(system)
    vocab_path = system / "ledger" / "facts" / "VOCAB.md"
    text = vocab_path.read_text().replace(
        "| term | kind | reason |\n|---|---|---|",
        "| term | kind | reason |\n|---|---|---|\n| `shoe_size` | predicate | too silly |",
    )
    vocab_path.write_text(text)
    rep = _check(system)
    assert any("retired vocabulary" in e.lower() for e in rep.errors)


def test_worklist_lists_open_interpretations_and_frontier(system: Path) -> None:
    _fact(system, "artist", {"id": "stub", "type": "artist", "name": "Stub"})
    _interp(system, {
        "id": "who-knows", "kind": "hypothesis", "about": ["stub"],
        "statement": "Stub might be from Quebec.", "confidence": "speculative",
        "reasoning": "r", "based_on": [f"corpus://{H_PUB}"],
        "needs": [{"action": "search", "why": "hometown source"}],
        "status": "open", "asof": "2026-07-02",
    })
    _regen(system)
    openq = (system / "ledger" / "open-questions.md").read_text()
    assert "**hypothesis** (speculative) `who-knows`" in openq
    assert "(search)" in openq
    assert "stub `stub` (artist)" in openq
    assert "## Curated" in openq  # content outside the block survives


# ----------------------------------------------------------------- cli surface


def test_ath_ledger_dispatch(system: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _fact(system, "artist", {"id": "x", "type": "artist", "name": "X"})
    _regen(system)
    assert ath_main(["ledger", "check", "--root", str(system)]) == 0
    out = capsys.readouterr().out
    assert "1 fact files" in out
    _fact(system, "artist", {"id": "bad", "type": "artist"})
    assert ath_main(["ledger", "check", "--root", str(system)]) == 1


def test_ledger_yaml_must_name_registered_corpora(system: Path) -> None:
    (system / "ledger" / "ledger.yaml").write_text("name: ledger\ncorpora: [nope]\n")
    assert ledger_main(["check", "--root", str(system)]) == 2
