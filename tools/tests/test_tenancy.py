"""Tenancy tiers (spec/ledger.md §6.4, v30): `record_tiers`' set-valued
derivation, the `*_visible` grant-intersection trio, and byte-identity of the
binary-specialized wrappers (`record_tenancy`, `evidence_entry_private`,
`claim_private_backed`, `fact_is_private`) against the pre-tier scalar
behavior every existing caller still rides."""

from __future__ import annotations

from pathlib import Path

import frontmatter
import pytest

from corpus import paths, records
from ledger import tenancy
from ledger.corpora import CorpusJoin, RegisteredCorpus

H_FAMILY = "1" * 64   # origin declares tenancy: family
H_PUBLIC = "2" * 64   # origin declares tenancy: public
H_PLAIN = "3" * 64    # no origin declaration — falls to the floor
H_MEMBER = "4" * 64   # promoted member, corpus:// lineage to H_FAMILY
H_LADDER = "5" * 64   # subtype-first ladder: base public, subtype private


def _mk(root: Path, h: str, *, origins: list[dict], touch: str = "corpus.ingest@0.1.0",
        ) -> None:
    post = frontmatter.Post(content="", **records.stub_frontmatter(record_id=h, touch_id=touch))
    records.set_artifact_block(post, mime="text/plain", fields={})
    for spec in origins:
        records.append_origin_block(post, **spec)
    records.dump(post, paths.record_path(root, h))


def _overlay(root: Path, relparts: list[str], tenancy_value: str) -> None:
    p = root / "schema" / "origin"
    p.mkdir(parents=True, exist_ok=True)
    for part in relparts[:-1]:
        p = p / part
        p.mkdir(parents=True, exist_ok=True)
    (p / f"{relparts[-1]}.yaml").write_text(f"tenancy: {tenancy_value}\n", encoding="utf-8")


@pytest.fixture()
def corpus_root(tmp_path: Path) -> Path:
    root = tmp_path / "corpus"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()

    _overlay(root, ["family-host"], "family")
    _mk(root, H_FAMILY, origins=[
        {"uri": "https://family-host/x", "snapshot": "2026-01-01T00:00:00Z",
         "schema_id": "family-host"},
    ])

    _overlay(root, ["pub-host"], "public")
    _mk(root, H_PUBLIC, origins=[
        {"uri": "https://pub-host/x", "snapshot": "2026-01-01T00:00:00Z",
         "schema_id": "pub-host"},
    ])

    _mk(root, H_PLAIN, origins=[
        {"uri": "https://unknown-host/x", "snapshot": "2026-01-01T00:00:00Z",
         "schema_id": None},
    ])

    _mk(root, H_MEMBER, origins=[
        {"uri": f"corpus://{H_FAMILY}?path=a.txt", "snapshot": "2026-01-01T00:00:00Z",
         "schema_id": None},
    ], touch="corpus.promote@0.1.0")

    _overlay(root, ["ladder-host"], "public")
    _overlay(root, ["ladder-host", "sub"], "private")
    _mk(root, H_LADDER, origins=[
        {"uri": "https://ladder-host/sub/x", "snapshot": "2026-01-01T00:00:00Z",
         "schema_id": "ladder-host", "subtype": "sub"},
    ])
    return root


_DECLARED = frozenset({"public", "private", "family"})


# ------------------------------------------------------------ record_tiers


def test_record_tiers_direct_declaration(corpus_root: Path) -> None:
    assert tenancy.record_tiers(corpus_root, H_FAMILY, declared=_DECLARED) == \
        frozenset({"family"})


def test_record_tiers_invalid_declaration_is_ignored(corpus_root: Path) -> None:
    """A declared value outside the instance's tier set is fail-closed: check
    reports the mismatch (ledger.check), derivation ignores it entirely and
    falls to the default — never invents a tier the instance didn't declare."""
    assert tenancy.record_tiers(corpus_root, H_FAMILY, default="private") == \
        frozenset({"private"})  # declared=None -> binary; "family" not valid


def test_record_tiers_union_across_origins(corpus_root: Path) -> None:
    h = "6" * 64
    _mk(corpus_root, h, origins=[
        {"uri": "https://family-host/a", "snapshot": "2026-01-01T00:00:00Z",
         "schema_id": "family-host"},
        {"uri": "https://pub-host/b", "snapshot": "2026-01-01T00:00:00Z",
         "schema_id": "pub-host"},
    ])
    assert tenancy.record_tiers(corpus_root, h, declared=_DECLARED) == \
        frozenset({"family", "public"})


def test_record_tiers_lineage_inheritance(corpus_root: Path) -> None:
    """A promoted member with no origin declaration of its own inherits its
    container's tiers through `corpus://` lineage, chased transitively."""
    assert tenancy.record_tiers(corpus_root, H_MEMBER, declared=_DECLARED) == \
        frozenset({"family"})


def test_record_tiers_no_declaration_falls_to_default(corpus_root: Path) -> None:
    assert tenancy.record_tiers(corpus_root, H_PLAIN, default="private",
                                declared=_DECLARED) == frozenset({"private"})
    assert tenancy.record_tiers(corpus_root, H_PLAIN, default="public",
                                declared=_DECLARED) == frozenset({"public"})


def test_record_tiers_unreadable_record_falls_to_default(corpus_root: Path) -> None:
    assert tenancy.record_tiers(corpus_root, "f" * 64, default="private") == \
        frozenset({"private"})


def test_record_tiers_subtype_ladder_most_specific_wins(corpus_root: Path) -> None:
    """§6.4's subtype-first ladder: `host/subtype` answers before the bare
    `host` rung — a more specific private declaration overrides a public
    base, exactly as the pre-tier scalar derivation's ladder did."""
    assert tenancy.record_tiers(corpus_root, H_LADDER, declared=_DECLARED) == \
        frozenset({"private"})


def test_record_tenancy_wrapper_byte_identical(corpus_root: Path) -> None:
    """The binary compatibility wrapper: `record_tenancy` collapses
    `record_tiers` to `"public"`/`"private"` — unaffected by tier values
    outside the binary (they're ignored, per fail-closed)."""
    assert tenancy.record_tenancy(corpus_root, H_PUBLIC) == "public"
    assert tenancy.record_tenancy(corpus_root, H_PLAIN, default="private") == "private"
    assert tenancy.record_tenancy(corpus_root, H_FAMILY, default="private") == "private"


# ------------------------------------------------------------- visibility trio


@pytest.fixture()
def join(corpus_root: Path) -> CorpusJoin:
    return CorpusJoin([RegisteredCorpus("corpus", corpus_root, private=True)])


def test_evidence_entry_visible_to_its_own_tier_only(join: CorpusJoin) -> None:
    entry = {"record": H_FAMILY}
    assert tenancy.evidence_entry_visible(entry, join, {}, frozenset({"family"}),
                                          declared=_DECLARED) is True
    assert tenancy.evidence_entry_visible(entry, join, {}, frozenset({"public"}),
                                          declared=_DECLARED) is False


def test_evidence_entry_visible_multi_tier_record(join: CorpusJoin, corpus_root: Path) -> None:
    h = "7" * 64
    _mk(corpus_root, h, origins=[
        {"uri": "https://family-host/a", "snapshot": "2026-01-01T00:00:00Z",
         "schema_id": "family-host"},
        {"uri": "https://pub-host/b", "snapshot": "2026-01-01T00:00:00Z",
         "schema_id": "pub-host"},
    ])
    entry = {"record": h}
    assert tenancy.evidence_entry_visible(entry, join, {}, frozenset({"family"}),
                                          declared=_DECLARED) is True
    assert tenancy.evidence_entry_visible(entry, join, {}, frozenset({"public"}),
                                          declared=_DECLARED) is True
    assert tenancy.evidence_entry_visible(entry, join, {}, frozenset({"accountant"}),
                                          declared=_DECLARED) is False


def test_evidence_entry_visible_unresolved_is_vacuous(join: CorpusJoin) -> None:
    """An unresolved citation contributes nothing — vacuously visible to any
    grants; `check` flags the dangle itself, elsewhere."""
    assert tenancy.evidence_entry_visible({"record": "f" * 64}, join, {}, frozenset()) \
        is True
    assert tenancy.evidence_entry_visible({}, join, {}, frozenset()) is True
    assert tenancy.evidence_entry_visible("not a dict", join, {}, frozenset()) is True


def test_claim_visible_requires_every_evidence_entry_visible(join: CorpusJoin) -> None:
    """§6.4: a claim is visible iff EVERY evidence entry is visible — mixed
    tier evidence needs a grant set covering both."""
    sources = {"a": {"record": H_FAMILY}, "b": {"record": H_PUBLIC}}
    claim = {
        "evidence": [{"source": "a"}, {"source": "b"}],
    }
    both = frozenset({"public", "family"})
    assert tenancy.claim_visible(claim, sources, join, {}, both, declared=_DECLARED) is True
    assert tenancy.claim_visible(claim, sources, join, {}, frozenset({"family"}),
                                 declared=_DECLARED) is False
    assert tenancy.claim_visible(claim, sources, join, {}, frozenset({"public"}),
                                 declared=_DECLARED) is False


def test_claim_visible_sensitivity_private_beats_everything(join: CorpusJoin) -> None:
    sources = {"a": {"record": H_PUBLIC}}
    claim = {"sensitivity": "private", "evidence": [{"source": "a"}]}
    every_tier = frozenset({"public", "private", "family", "accountant"})
    assert tenancy.claim_visible(claim, sources, join, {}, every_tier,
                                 declared=_DECLARED) is False


def test_fact_visible_bare_stub_is_visible(join: CorpusJoin) -> None:
    """A fact with no claims and no roster carries nothing to derive
    visibility FROM — never hidden by this rule alone, for any grants."""
    assert tenancy.fact_visible({"id": "x"}, join, {}, frozenset()) is True


def test_fact_visible_any_carried_visible(join: CorpusJoin) -> None:
    sources = {"a": {"record": H_FAMILY}, "b": {"record": H_PUBLIC}}
    fact = {
        "sources": sources,
        "claims": [
            {"id": "x:a", "evidence": [{"source": "a"}]},
            {"id": "x:b", "evidence": [{"source": "b"}]},
        ],
    }
    assert tenancy.fact_visible(fact, join, {}, frozenset({"family"}),
                                declared=_DECLARED) is True
    assert tenancy.fact_visible(fact, join, {}, frozenset({"accountant"}),
                                declared=_DECLARED) is False


def test_fact_visible_sensitivity_private_beats_everything(join: CorpusJoin) -> None:
    fact = {"sensitivity": "private", "claims": [
        {"id": "x:a", "evidence": [{"source": "a"}]},
    ], "sources": {"a": {"record": H_PUBLIC}}}
    assert tenancy.fact_visible(fact, join, {}, frozenset({"public", "family"})) is False


# ------------------------------------------------------- binary byte-identity


def test_evidence_entry_private_is_not_visible_to_public(join: CorpusJoin) -> None:
    for entry in ({"record": H_FAMILY}, {"record": H_PUBLIC}, {"record": "f" * 64}, {}):
        assert tenancy.evidence_entry_private(entry, join, {}) == \
            (not tenancy.evidence_entry_visible(entry, join, {}, frozenset({"public"})))


def test_claim_private_backed_is_not_visible_to_public(join: CorpusJoin) -> None:
    sources = {"a": {"record": H_FAMILY}, "b": {"record": H_PUBLIC}}
    for claim in (
        {"evidence": [{"source": "a"}]},
        {"evidence": [{"source": "b"}]},
        {"evidence": [{"source": "a"}, {"source": "b"}]},
        {"sensitivity": "private", "evidence": [{"source": "b"}]},
    ):
        assert tenancy.claim_private_backed(claim, sources, join, {}) == (
            not tenancy.claim_visible(claim, sources, join, {}, frozenset({"public"}))
        )


def test_fact_is_private_is_not_visible_to_public(join: CorpusJoin) -> None:
    sources = {"a": {"record": H_FAMILY}, "b": {"record": H_PUBLIC}}
    for fact in (
        {"claims": [{"id": "x:a", "evidence": [{"source": "a"}]}], "sources": sources},
        {"claims": [{"id": "x:b", "evidence": [{"source": "b"}]}], "sources": sources},
        {"id": "bare"},
        {"sensitivity": "private", "claims": [], "sources": sources},
    ):
        assert tenancy.fact_is_private(fact, join, {}) == (
            not tenancy.fact_visible(fact, join, {}, frozenset({"public"}))
        )
