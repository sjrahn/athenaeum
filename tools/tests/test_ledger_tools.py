"""The ledger's deterministic tooling: harvest (§10), evidence verification
(§13.2), promote/stamp (§7.2, §7.3), worklist, coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.coverage import render_coverage, represented_hashes
from ledger.harvest import HarvestError, load_rules, match, run_harvest
from ledger.model import canonical_claim_state, derived_uri
from ledger.promote import PromoteError, promote, stamp
from ledger.verify import verify_ledger
from ledger.worklist import worklist

H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64
H4 = "4" * 64


def _imessage_record(root: Path, h: str, handle, period: str) -> None:
    p = root / "records" / h[:2] / f"{h}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(handle, list):
        handle_yaml = "handle:\n" + "".join(f"- '{x}'\n" for x in handle)
    else:
        handle_yaml = f"handle: '{handle}'\n"
    p.write_text(
        f"---\nid: {h}\ntitle: ''\nstatus: normalized\n"
        "touch:\n- corpus.ingest@0.1.0\n- corpus.compile@0.1.0\n---\n\n"
        "<!--artifact text/html\n-->\n\n"
        f"<!--origin imessage-export\nsnapshot: '2026-07-01T00:00:00Z'\n"
        f"period: {period}\n{handle_yaml}-->\n\n"
        "<!--segment text/message\naddress: el=1\nsender: Me\n-->\n"
        "hello from the fixture\n<!--/segment-->\n",
        encoding="utf-8",
    )


def _promoted_member_record(root: Path, h: str, container_h: str) -> None:
    """A promoted member's origin `uri:` is `corpus://<container>?…`
    (spec/corpus.md §1.2) — its lineage origin, not a captured web URL."""
    p = root / "records" / h[:2] / f"{h}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nid: {h}\ntitle: ''\nstatus: normalized\n"
        "touch:\n- corpus.ingest@0.1.0\n---\n\n"
        "<!--artifact text/plain\n-->\n\n"
        f"<!--origin container-lineage\nuri: 'corpus://{container_h}?stream_id=1'\n-->\n",
        encoding="utf-8",
    )


def _reattributed_member_record(root: Path, h: str, container_h: str) -> None:
    """A record whose FIRST origin block is a now-retired container's lineage,
    later re-attributed to a live web origin (a v32 envelope collapse: the
    container is removed, the payload lives on standalone) — a fresh origin
    block APPENDED after the containment one, per §5.2's append-only history.
    The live lineage is the LATEST block, the web one."""
    p = root / "records" / h[:2] / f"{h}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nid: {h}\ntitle: ''\nstatus: normalized\n"
        "touch:\n- corpus.ingest@0.1.0\n---\n\n"
        "<!--artifact text/plain\n-->\n\n"
        f"<!--origin container-lineage\nuri: 'corpus://{container_h}?stream_id=1'\n-->\n\n"
        "<!--origin web\nuri: 'https://example.com/reattributed'\n"
        "snapshot: '2026-08-01T00:00:00Z'\n-->\n",
        encoding="utf-8",
    )


@pytest.fixture()
def system(tmp_path: Path) -> Path:
    root = tmp_path
    (root / "athenaeum.yaml").write_text(
        "org: https://example.test/org\n"
        "corpora:\n  corpus-private:\n    visibility: private\n"
        "ledger:\n  ledger:\n"
    )
    priv = root / "corpora" / "corpus-private"
    _imessage_record(priv, H1, "+14035551234", "2023-03")
    _imessage_record(priv, H2, "+14035551234", "2023-04")  # same chat, next window
    _imessage_record(priv, H3, ["+1403", "+1587"], "2023-03")  # group: never mints
    ledger = root / "ledger"
    (ledger / "facts").mkdir(parents=True)
    (ledger / "interpretations").mkdir()
    (ledger / "harvest").mkdir()
    (ledger / "ledger.yaml").write_text("name: ledger\ncorpora: [corpus-private]\n")
    (ledger / "open-questions.md").write_text(
        "# Open questions\n\n<!--worklist:begin-->\n<!--worklist:end-->\n"
    )
    (ledger / "harvest" / "chats.yaml").write_text(
        "id: chats\ndescription: test\n"
        "match:\n"
        "  origin.id: {equals: imessage-export}\n"
        "  origin.handle: {matches: '^\\+?[0-9]+$'}\n"
        "mint:\n"
        "  concept: {id: 'chat-{origin.handle}', type: conversation,\n"
        "            name: 'Chat {origin.handle}'}\n"
        "  roster: [{role: transcript}]\n"
        "  claims:\n"
        "    - {predicate: window, value: '{origin.period}', evidence_kind: direct}\n"
    )
    return root


def _corpora(root: Path) -> list[RegisteredCorpus]:
    return [RegisteredCorpus("corpus-private", root / "corpora" / "corpus-private",
                             private=True)]


def test_harvest_converges_by_origin_native_key(system: Path) -> None:
    run = run_harvest(system / "ledger", _corpora(system))
    assert run.minted == 1  # two windows, one chat; the group minted nothing
    concept = json.loads(
        (system / "ledger" / "facts" / "conversation" / "chat-14035551234.json").read_text()
    )
    assert concept["provenance"] == "auto"
    assert {e["uri"] for e in concept["artifacts"]} == {f"corpus://{H1}", f"corpus://{H2}"}
    assert all(e["provenance"] == "auto" for e in concept["artifacts"])
    windows = {c["value"] for c in concept["claims"] if c["predicate"] == "window"}
    assert windows == {"2023-03", "2023-04"}
    assert all(c["status"] == "provisional" for c in concept["claims"])
    # claim evidence cites the sources table — one entry per distinct record,
    # deduplicated (the table's whole point) rather than one per claim
    sources = concept["sources"]
    assert {entry["record"] for entry in sources.values()} == {H1, H2}
    cited = {derived_uri(sources, e["source"], e.get("anchor"))
             for c in concept["claims"] for e in c["evidence"]}
    assert cited == {f"corpus://{H1}", f"corpus://{H2}"}
    # idempotent: strip + re-mint converges (sources table included, byte-for-byte)
    again = run_harvest(system / "ledger", _corpora(system))
    assert again.stripped_files == 1 and again.minted == 1
    assert json.loads(
        (system / "ledger" / "facts" / "conversation" / "chat-14035551234.json").read_text()
    ) == concept


def test_harvest_asserted_wins(system: Path) -> None:
    run_harvest(system / "ledger", _corpora(system))
    p = system / "ledger" / "facts" / "conversation" / "chat-14035551234.json"
    concept = json.loads(p.read_text())
    del concept["provenance"]  # a human adopts the concept
    concept["name"] = "Texts with Mom"
    concept["claims"] = [c for c in concept["claims"]
                         if c["value"] != "2023-03"]  # keep one auto claim out
    p.write_text(json.dumps(concept, indent=2))
    run = run_harvest(system / "ledger", _corpora(system))
    assert run.stripped_files == 0  # the adopted file survives the strip
    after = json.loads(p.read_text())
    assert after["name"] == "Texts with Mom"  # harvest never touches asserted content
    assert {c["value"] for c in after["claims"]} == {"2023-03", "2023-04"}  # re-converged
    # both claims were still individually auto-marked, so BOTH got stripped and
    # re-minted — the sources table converges the same way, never left orphaned
    hashes = {entry["record"] for entry in after["sources"].values()}
    assert hashes == {H1, H2}


def test_hash_only_rules_may_not_mint(tmp_path: Path) -> None:
    (tmp_path / "harvest").mkdir()
    (tmp_path / "harvest" / "bad.yaml").write_text(
        "id: bad\nmatch: {mime: {equals: text/html}}\n"
        "mint: {concept: {id: static-thing, type: thing, name: X}}\n"
    )
    with pytest.raises(HarvestError, match="interpolates no origin fact"):
        load_rules(tmp_path)


def test_classify_when_invalid_regex_raises_harvest_error() -> None:
    """`match`'s operator evaluation is the shared §10 implementation
    (`ledger.scope.op_matches`) — its ValueError (an invalid `matches`
    pattern isn't a ValueError subclass by itself, `re.error` is) must
    surface here as this module's own `HarvestError`, never a bare
    `re.error`/`ValueError` escaping harvest's boundary."""
    with pytest.raises(HarvestError, match="not a valid regex"):
        match({"origin.handle": {"matches": "["}}, {"origin.handle": "+14035551234"})


def test_classify_when_redos_prone_pattern_raises_harvest_error() -> None:
    """finding 9c at harvest's boundary: a catastrophic-backtracking-prone
    pattern is refused at validation (wrapped into HarvestError), never
    actually executed against fact data."""
    with pytest.raises(HarvestError, match=r"catastrophic|nested"):
        match({"origin.handle": {"matches": r"(\w+\s?)*"}}, {"origin.handle": "x"})


def test_verify_quotes_and_anchors(system: Path) -> None:
    ledger = system / "ledger"
    (ledger / "facts" / "person").mkdir()
    (ledger / "facts" / "person" / "mom.json").write_text(json.dumps({
        "id": "mom", "type": "person", "name": "Mom",
        # each citation gets its OWN source key here (not the sources-table
        # dedup a real fact would use) so this test can probe per-entry
        # verification independent of the shared-source stamping rule —
        # that rule gets its own dedicated test below
        "sources": {"s1": {"record": H1}, "s2": {"record": H1}, "s3": {"record": H1}},
        "claims": [
            {"id": "mom:greeting", "predicate": "greeting", "value": "x",
             "status": "confirmed", "asof": "2023-03-01",
             "evidence": [{"source": "s1", "anchor": "el=1",
                           "quote": "hello from   the fixture", "kind": "authoritative"}]},
            {"id": "mom:bogus-quote", "predicate": "bogus", "value": "x",
             "status": "confirmed", "asof": "2023-03-01",
             "evidence": [{"source": "s2", "anchor": "el=1",
                           "quote": "never said this", "kind": "authoritative"}]},
            {"id": "mom:bad-anchor", "predicate": "bogus2", "value": "x",
             "status": "provisional", "asof": "2023-03-01",
             "evidence": [{"source": "s3", "anchor": "el=99", "kind": "direct"}]},
        ],
    }))
    join = CorpusJoin(_corpora(system))
    res = verify_ledger(ledger, join, {}, stamp=True, today="2026-07-02")
    assert res.verified == 1 and res.stamped == 1
    assert any("quote not found" in e for e in res.errors)          # confirmed → error
    assert any("anchor does not resolve" in w for w in res.warnings)  # provisional → warn
    fact = json.loads((ledger / "facts" / "person" / "mom.json").read_text())
    stamped = fact["sources"]["s1"]["verified"]
    assert stamped == {"touch": "corpus.compile@0.1.0", "at": "2026-07-02"}
    # drift: the pin excludes sources-entry `verified` stamps, so stamping
    # didn't move the canonical state
    unstamped = {k: {kk: vv for kk, vv in v.items() if kk != "verified"}
                 for k, v in fact["sources"].items()}
    assert canonical_claim_state(fact["claims"][0], fact["sources"]) == \
        canonical_claim_state(fact["claims"][0], unstamped)
    # a later-day re-run must NOT re-stamp: only a moved touch identity may
    # rewrite fact files (else every verify run churns the whole tree)
    res2 = verify_ledger(ledger, join, {}, stamp=True, today="2026-07-03")
    assert res2.verified == 1 and res2.stamped == 0
    fact2 = json.loads((ledger / "facts" / "person" / "mom.json").read_text())
    assert fact2["sources"]["s1"]["verified"]["at"] == "2026-07-02"


def test_verify_shared_source_stamps_only_if_all_citations_pass(system: Path) -> None:
    """A source is stamped ONLY when every evidence entry citing it this run
    reached the verified tail — a genuine failure on one citation must not
    certify the shared record as freshly checked for the others."""
    ledger = system / "ledger"
    (ledger / "facts" / "person").mkdir()
    (ledger / "facts" / "person" / "dad.json").write_text(json.dumps({
        "id": "dad", "type": "person", "name": "Dad",
        "sources": {"s1": {"record": H1}},
        "claims": [
            {"id": "dad:good", "predicate": "greeting", "value": "x",
             "status": "provisional", "asof": "2023-03-01",
             "evidence": [{"source": "s1", "anchor": "el=1",
                           "quote": "hello from   the fixture", "kind": "direct"}]},
            {"id": "dad:bad", "predicate": "bogus", "value": "x",
             "status": "provisional", "asof": "2023-03-01",
             "evidence": [{"source": "s1", "anchor": "el=1",
                           "quote": "never said this", "kind": "direct"}]},
        ],
    }))
    join = CorpusJoin(_corpora(system))
    res = verify_ledger(ledger, join, {}, stamp=True, today="2026-07-02")
    assert res.verified == 1  # dad:good's citation
    assert res.stamped == 0   # s1 is shared with dad:bad's failing citation
    fact = json.loads((ledger / "facts" / "person" / "dad.json").read_text())
    assert "verified" not in fact["sources"]["s1"]


def test_verify_embed_descriptions_and_inline_markup(system: Path) -> None:
    """Embed descriptions are citable record content (§13.2) — the parsed
    block carries them under `fields`, and verification must read that home
    (the 2026-07-03 extraction pass found them silently invisible). Inline
    presentational markup (`<u>…</u>`) vanishes at normalization, so a quote
    cites the rendered text straight through it."""
    h4 = "4" * 64
    p = system / "corpora" / "corpus-private" / "records" / h4[:2] / f"{h4}.md"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(
        f"---\nid: {h4}\ntitle: ''\nstatus: normalized\n"
        "touch:\n- corpus.ingest@0.1.0\n- corpus.compile@0.1.0\n---\n\n"
        "<!--artifact text/html\n-->\n\n"
        "<!--origin imessage-export\nsnapshot: '2026-07-01T00:00:00Z'\n"
        "period: 2025-05\nhandle: '+14035551234'\n-->\n\n"
        f"<!--embed image/jpeg\naddress: el=2\ntransport: blake3:{'a' * 64}\n"
        "description: a cat with pricked ears sits watching the screen\n-->\n\n"
        "<!--segment text/message\naddress: el=1\nsender: Me\n-->\n"
        "the wedding is <u>Oct 26th</u> in revy\n<!--/segment-->\n",
        encoding="utf-8",
    )
    ledger = system / "ledger"
    (ledger / "facts" / "person").mkdir()
    (ledger / "facts" / "person" / "kat.json").write_text(json.dumps({
        "id": "kat", "type": "person", "name": "Kat",
        "sources": {"s1": {"record": h4}},
        "claims": [
            {"id": "kat:cat", "predicate": "possession", "value": "a cat",
             "status": "provisional", "asof": "2025-05-31",
             "evidence": [{"source": "s1", "anchor": "el=2",
                           "quote": "a cat with pricked ears", "kind": "incidental"}]},
            {"id": "kat:wedding", "predicate": "description", "value": "x",
             "status": "provisional", "asof": "2025-05-31",
             "evidence": [{"source": "s1", "anchor": "el=1",
                           "quote": "the wedding is Oct 26th in revy",
                           "kind": "direct"}]},
        ],
    }))
    join = CorpusJoin(_corpora(system))
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 2
    assert not res.errors and not res.warnings


def _ref_fact(ledger: Path, sources: dict, claims: list) -> None:
    (ledger / "facts" / "band").mkdir(parents=True, exist_ok=True)
    (ledger / "facts" / "band" / "acme.json").write_text(json.dumps({
        "id": "acme", "type": "band", "name": "Acme",
        "sources": sources, "claims": claims,
    }))


def test_verify_ref_bare_binds_latest_and_restamps_only_on_change(system: Path) -> None:
    """§13.2.3: a bare `ref://` citation resolves through the dataset's
    `latest` tag and stamps `{snapshot, artifact}` — content stays
    unverifiable (no adapter exists yet) without blocking the stamp."""
    from ath.manifest import Reference, Snapshot

    ledger = system / "ledger"
    v1 = "a" * 64
    _ref_fact(ledger, {"s1": {"ref": "musicbrainz/artist/abc-123"}}, [
        {"id": "acme:mb-id", "predicate": "musicbrainz-id", "value": "abc-123",
         "status": "confirmed", "asof": "2026-07-02",
         "evidence": [{"source": "s1", "kind": "authoritative"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets = {"musicbrainz": Reference(dataset="musicbrainz", description="test",
                                          adapter="jsonl-index", latest="2026-01",
                                          snapshots={"2026-01": Snapshot(artifact=v1)})}
    res = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-02")
    assert res.unverifiable == 1  # content: no adapter yet — every registered case
    assert res.stamped == 1
    assert not res.errors and not res.warnings
    fact = json.loads((ledger / "facts" / "band" / "acme.json").read_text())
    assert fact["sources"]["s1"]["verified"] == {
        "snapshot": "2026-01", "artifact": v1, "at": "2026-07-02"}
    # unchanged (tag, artifact) on a later run must not rewrite the binding
    res2 = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-03")
    assert res2.stamped == 0
    fact2 = json.loads((ledger / "facts" / "band" / "acme.json").read_text())
    assert fact2["sources"]["s1"]["verified"]["at"] == "2026-07-02"


def test_verify_ref_pinned_binds_pinned_tags_artifact(system: Path) -> None:
    from ath.manifest import Reference, Snapshot

    ledger = system / "ledger"
    v1, v2 = "a" * 64, "b" * 64
    _ref_fact(ledger, {"s1": {"ref": "musicbrainz@2025-01/artist/abc-123"}}, [
        {"id": "acme:mb-id", "predicate": "musicbrainz-id", "value": "abc-123",
         "status": "confirmed", "asof": "2025-06-01",
         "evidence": [{"source": "s1", "kind": "authoritative"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets = {"musicbrainz": Reference(
        dataset="musicbrainz", description="test", adapter="jsonl-index", latest="2026-01",
        snapshots={"2025-01": Snapshot(artifact=v1), "2026-01": Snapshot(artifact=v2)})}
    res = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-02")
    assert res.unverifiable == 1
    assert res.stamped == 1
    fact = json.loads((ledger / "facts" / "band" / "acme.json").read_text())
    assert fact["sources"]["s1"]["verified"] == {
        "snapshot": "2025-01", "artifact": v1, "at": "2026-07-02"}


def test_verify_ref_latest_bump_drifts_bare_cite_only(system: Path) -> None:
    """A moved `latest` flags every bare citer for re-verification; a pinned
    citation is drift-free by construction (§6.5, §13.2.3)."""
    from ath.manifest import Reference, Snapshot

    ledger = system / "ledger"
    v1, v2 = "a" * 64, "b" * 64
    _ref_fact(ledger, {
        "s1": {"ref": "musicbrainz/artist/abc-123"},
        "s2": {"ref": "musicbrainz@2026-01/artist/abc-123"},
    }, [
        {"id": "acme:mb-bare", "predicate": "musicbrainz-id", "value": "abc-123",
         "status": "confirmed", "asof": "2026-07-02",
         "evidence": [{"source": "s1", "kind": "authoritative"}]},
        {"id": "acme:mb-pinned", "predicate": "musicbrainz-id", "value": "abc-123",
         "status": "confirmed", "asof": "2026-07-02",
         "evidence": [{"source": "s2", "kind": "authoritative"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets_v1 = {"musicbrainz": Reference(dataset="musicbrainz", description="test",
                                             adapter="jsonl-index", latest="2026-01",
                                             snapshots={"2026-01": Snapshot(artifact=v1)})}
    verify_ledger(ledger, join, datasets_v1, stamp=True, today="2026-07-02")
    datasets_v2 = {"musicbrainz": Reference(
        dataset="musicbrainz", description="test", adapter="jsonl-index", latest="2026-02",
        snapshots={"2026-01": Snapshot(artifact=v1), "2026-02": Snapshot(artifact=v2)})}
    res = verify_ledger(ledger, join, datasets_v2, stamp=False, today="2026-07-03")
    drift = [w for w in res.warnings if "snapshot binding drifted" in w]
    assert len(drift) == 1
    assert "acme:mb-bare" in drift[0]
    assert "acme:mb-pinned" not in drift[0]


def test_verify_ref_pinned_artifact_repointed_drifts(system: Path) -> None:
    """A pin's residual failure mode: the manifest re-points the pinned tag's
    mirror-artifact hash out from under a frozen citation (§13.2.3 — the hash
    is the true pin)."""
    from ath.manifest import Reference, Snapshot

    ledger = system / "ledger"
    v1, v2 = "a" * 64, "b" * 64
    _ref_fact(ledger, {"s1": {"ref": "musicbrainz@2025-01/artist/abc-123"}}, [
        {"id": "acme:mb-id", "predicate": "musicbrainz-id", "value": "abc-123",
         "status": "confirmed", "asof": "2025-06-01",
         "evidence": [{"source": "s1", "kind": "authoritative"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets_v1 = {"musicbrainz": Reference(dataset="musicbrainz", description="test",
                                             adapter="jsonl-index", latest="2025-01",
                                             snapshots={"2025-01": Snapshot(artifact=v1)})}
    verify_ledger(ledger, join, datasets_v1, stamp=True, today="2026-07-02")
    datasets_repointed = {"musicbrainz": Reference(
        dataset="musicbrainz", description="test", adapter="jsonl-index",
        latest="2025-01", snapshots={"2025-01": Snapshot(artifact=v2)})}
    res = verify_ledger(ledger, join, datasets_repointed, stamp=False, today="2026-07-03")
    assert any("snapshot binding drifted" in w for w in res.warnings)


def test_verify_ref_unregistered_dataset_and_dangling_pin_are_unverifiable(
    system: Path,
) -> None:
    """No crash, no stamp — check owns the hard error for both (§13.1); verify
    stays honestly unverifiable."""
    from ath.manifest import Reference, Snapshot

    ledger = system / "ledger"
    _ref_fact(ledger, {
        "s1": {"ref": "wikidata/artist/abc-123"},           # unregistered dataset
        "s2": {"ref": "musicbrainz@2099-01/artist/abc-123"},  # dangling pin
    }, [
        {"id": "acme:unreg", "predicate": "x", "value": "x",
         "status": "provisional", "asof": "2026-07-02",
         "evidence": [{"source": "s1", "kind": "incidental"}]},
        {"id": "acme:dangling", "predicate": "x", "value": "x",
         "status": "provisional", "asof": "2026-07-02",
         "evidence": [{"source": "s2", "kind": "incidental"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets = {"musicbrainz": Reference(dataset="musicbrainz", description="test",
                                          adapter="jsonl-index", latest="2026-01",
                                          snapshots={"2026-01": Snapshot(artifact="a" * 64)})}
    res = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-02")
    assert res.unverifiable == 2
    assert res.stamped == 0
    assert not res.errors  # a validation-error class, not verify's to raise
    fact = json.loads((ledger / "facts" / "band" / "acme.json").read_text())
    assert "verified" not in fact["sources"]["s1"]
    assert "verified" not in fact["sources"]["s2"]


def _ref_zim_path(tmp_path: Path) -> Path:
    """A tiny fixture mirror standing in for a `ref://` dataset (§6.5): one
    text entry a quote can hit or miss, one image entry with no text
    projection. Local copy of `test_refdata.py`'s fixture pattern — this
    suite doesn't import across test modules."""
    import libzim.writer as zw

    class _Item(zw.Item):
        def __init__(self, path: str, title: str, content, mimetype: str):
            super().__init__()
            self._path, self._title = path, title
            self._content, self._mimetype = content, mimetype

        def get_path(self) -> str:
            return self._path

        def get_title(self) -> str:
            return self._title

        def get_mimetype(self) -> str:
            return self._mimetype

        def get_contentprovider(self):
            return zw.StringProvider(self._content)

        def get_hints(self) -> dict:
            return {zw.Hint.FRONT_ARTICLE: 1}

    p = tmp_path / "musicbrainz.zim"
    with zw.Creator(str(p)) as creator:
        creator.add_item(_Item(
            "artist/abc-123", "Acme",
            "<html><body><p>Acme is a fictional test band from "
            "Testville.</p></body></html>", "text/html"))
        creator.add_item(_Item("artist/no-text", "No Text",
                               b"\x89PNG\r\n\x1a\n" + b"\x00" * 16, "image/png"))
        creator.set_mainpath("artist/abc-123")
    return p


def _mb_reference(tag: str, artifact: str, *, adapter: str = "zim", path: str | None = None):
    from ath.manifest import Reference, Snapshot

    return Reference(dataset="musicbrainz", description="test", adapter=adapter,
                     latest=tag, snapshots={tag: Snapshot(artifact=artifact, path=path)})


def test_verify_ref_quote_found_counts_verified_and_stamps(system: Path) -> None:
    """*(Phase 1, §6.5/§13.2.2)* A ref citation's quote checks against the
    adapter's rendered entry — found, it counts toward `verified` and the
    resolution binding still stamps."""
    pytest.importorskip("libzim")
    zim_path = _ref_zim_path(system)
    ledger = system / "ledger"
    v1 = "a" * 64
    _ref_fact(ledger, {"s1": {"ref": "musicbrainz/artist/abc-123"}}, [
        {"id": "acme:tagline", "predicate": "tagline", "value": "x",
         "status": "confirmed", "asof": "2026-07-02",
         "evidence": [{"source": "s1", "quote": "fictional test band from Testville",
                       "kind": "authoritative"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets = {"musicbrainz": _mb_reference("t", v1, path=str(zim_path))}
    res = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-02")
    assert res.verified == 1
    assert res.stamped == 1
    assert not res.errors and not res.warnings
    fact = json.loads((ledger / "facts" / "band" / "acme.json").read_text())
    assert fact["sources"]["s1"]["verified"] == {
        "snapshot": "t", "artifact": v1, "at": "2026-07-02"}


def test_verify_ref_quote_absent_fails_at_claim_severity_no_stamp(system: Path) -> None:
    pytest.importorskip("libzim")
    zim_path = _ref_zim_path(system)
    ledger = system / "ledger"
    v1 = "a" * 64
    _ref_fact(ledger, {"s1": {"ref": "musicbrainz/artist/abc-123"}}, [
        {"id": "acme:bogus", "predicate": "bogus", "value": "x",
         "status": "confirmed", "asof": "2026-07-02",
         "evidence": [{"source": "s1", "quote": "this never appears anywhere",
                       "kind": "authoritative"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets = {"musicbrainz": _mb_reference("t", v1, path=str(zim_path))}
    res = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-02")
    assert res.verified == 0
    assert res.stamped == 0
    assert any("quote not found" in e for e in res.errors)  # confirmed → error
    fact = json.loads((ledger / "facts" / "band" / "acme.json").read_text())
    assert "verified" not in fact["sources"]["s1"]


def test_verify_ref_entry_not_found_fails_no_stamp(system: Path) -> None:
    pytest.importorskip("libzim")
    zim_path = _ref_zim_path(system)
    ledger = system / "ledger"
    v1 = "a" * 64
    _ref_fact(ledger, {"s1": {"ref": "musicbrainz/artist/does-not-exist"}}, [
        {"id": "acme:missing", "predicate": "x", "value": "x",
         "status": "confirmed", "asof": "2026-07-02",
         "evidence": [{"source": "s1", "kind": "authoritative"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets = {"musicbrainz": _mb_reference("t", v1, path=str(zim_path))}
    res = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-02")
    assert res.stamped == 0
    assert any("names no entry" in e for e in res.errors)
    fact = json.loads((ledger / "facts" / "band" / "acme.json").read_text())
    assert "verified" not in fact["sources"]["s1"]


def test_verify_ref_adapter_unavailable_stamps_unverifiable(system: Path) -> None:
    """An unregistered adapter name is an honest environment gap (§6.5) —
    unverifiable, but the resolution binding still stamps (unchanged from
    Phase 0 for this specific gap)."""
    ledger = system / "ledger"
    v1 = "a" * 64
    _ref_fact(ledger, {"s1": {"ref": "musicbrainz/artist/abc-123"}}, [
        {"id": "acme:mb-id", "predicate": "musicbrainz-id", "value": "abc-123",
         "status": "confirmed", "asof": "2026-07-02",
         "evidence": [{"source": "s1", "quote": "irrelevant", "kind": "authoritative"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets = {"musicbrainz": _mb_reference("t", v1, adapter="nonexistent")}
    res = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-02")
    assert res.unverifiable == 1
    assert res.stamped == 1
    assert not res.errors and not res.warnings
    fact = json.loads((ledger / "facts" / "band" / "acme.json").read_text())
    assert fact["sources"]["s1"]["verified"] == {
        "snapshot": "t", "artifact": v1, "at": "2026-07-02"}


def test_verify_ref_mirror_absent_stamps_unverifiable(system: Path) -> None:
    """No `path:` override and no corpus store holds the artifact — a mirror
    gap, honestly unverifiable, still stamps the resolution binding. (Works
    whether or not `libzim` is installed: an unavailable adapter and an
    absent mirror degrade identically here, so this doesn't need gating.)"""
    ledger = system / "ledger"
    v1 = "a" * 64
    _ref_fact(ledger, {"s1": {"ref": "musicbrainz/artist/abc-123"}}, [
        {"id": "acme:mb-id", "predicate": "musicbrainz-id", "value": "abc-123",
         "status": "confirmed", "asof": "2026-07-02",
         "evidence": [{"source": "s1", "kind": "authoritative"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets = {"musicbrainz": _mb_reference("t", v1)}  # no path:, no corpus store entry
    res = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-02")
    assert res.unverifiable == 1
    assert res.stamped == 1
    assert not res.errors and not res.warnings
    fact = json.loads((ledger / "facts" / "band" / "acme.json").read_text())
    assert fact["sources"]["s1"]["verified"] == {
        "snapshot": "t", "artifact": v1, "at": "2026-07-02"}


def test_verify_ref_no_quote_existence_citation_verified(system: Path) -> None:
    pytest.importorskip("libzim")
    zim_path = _ref_zim_path(system)
    ledger = system / "ledger"
    v1 = "a" * 64
    _ref_fact(ledger, {"s1": {"ref": "musicbrainz/artist/abc-123"}}, [
        {"id": "acme:mb-id", "predicate": "musicbrainz-id", "value": "abc-123",
         "status": "confirmed", "asof": "2026-07-02",
         "evidence": [{"source": "s1", "kind": "authoritative"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets = {"musicbrainz": _mb_reference("t", v1, path=str(zim_path))}
    res = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-02")
    assert res.verified == 1
    assert res.stamped == 1
    assert not res.errors and not res.warnings


def test_verify_ref_no_text_projection_unverifiable_stamp_proceeds(system: Path) -> None:
    """(§6.5) An entry with no text projection (an image) — the quote is
    held, not wrong: unverifiable, but the stamp still proceeds."""
    pytest.importorskip("libzim")
    zim_path = _ref_zim_path(system)
    ledger = system / "ledger"
    v1 = "a" * 64
    _ref_fact(ledger, {"s1": {"ref": "musicbrainz/artist/no-text"}}, [
        {"id": "acme:cover-art", "predicate": "cover-art", "value": "x",
         "status": "confirmed", "asof": "2026-07-02",
         "evidence": [{"source": "s1", "quote": "anything", "kind": "incidental"}]},
    ])
    join = CorpusJoin(_corpora(system))
    datasets = {"musicbrainz": _mb_reference("t", v1, path=str(zim_path))}
    res = verify_ledger(ledger, join, datasets, stamp=True, today="2026-07-02")
    assert res.unverifiable == 1
    assert res.stamped == 1
    assert not res.errors and not res.warnings


def test_promote_and_stamp(system: Path) -> None:
    ledger = system / "ledger"
    (ledger / "facts" / "person").mkdir()
    (ledger / "facts" / "person" / "mom.json").write_text(json.dumps({
        "id": "mom", "type": "person", "name": "Mom",
        "sources": {"s1": {"record": H1}},
        "claims": [{"id": "mom:phone", "predicate": "phone", "value": "+1403",
                    "status": "provisional", "asof": "2023-03-01",
                    "evidence": [{"source": "s1", "kind": "direct"}]}],
    }))
    (ledger / "interpretations" / "mom-birthday.json").write_text(json.dumps({
        "id": "mom-birthday", "kind": "hypothesis", "about": ["mom"],
        "statement": "Mom's birthday is in June.", "confidence": "likely",
        "reasoning": "r", "based_on": [f"corpus://{H1}"],
        # `proposes` predates the fact it targets, so it stays inline-uri
        # shaped — `promote` hoists it into the target's sources table
        "proposes": {"id": "mom:birthday", "predicate": "birthday", "value": "June",
                     "evidence": [{"uri": f"corpus://{H1}", "kind": "authoritative"}]},
        "status": "open", "asof": "2026-07-02",
    }))
    landed = promote(ledger, "mom-birthday")
    assert landed == "mom:birthday (confirmed)"  # authoritative evidence passes the bar
    fact = json.loads((ledger / "facts" / "person" / "mom.json").read_text())
    birthday = next(c for c in fact["claims"] if c["id"] == "mom:birthday")
    assert "uri" not in birthday["evidence"][0]  # landed source-keyed, not inline
    skey = birthday["evidence"][0]["source"]
    # the pre-existing sources entry for H1 (from mom:phone) is REUSED, not duplicated
    assert skey == "s1"
    assert fact["sources"] == {"s1": {"record": H1}}
    interp = json.loads((ledger / "interpretations" / "mom-birthday.json").read_text())
    assert interp["status"] == "promoted" and interp["resolution"] == "mom:birthday"
    # the interpretation's own proposes stays inline-uri shaped — untouched
    assert interp["proposes"]["evidence"][0]["uri"] == f"corpus://{H1}"
    with pytest.raises(PromoteError, match="not open"):
        promote(ledger, "mom-birthday")

    (ledger / "interpretations" / "phone-wrong.json").write_text(json.dumps({
        "id": "phone-wrong", "kind": "correction", "about": ["mom"],
        "statement": "mom:phone misreads the source.", "reasoning": "r",
        "based_on": [f"corpus://{H1}"],
        "challenges": {"claim": "mom:phone"},
        "status": "standing", "asof": "2026-07-02",
    }))
    state = stamp(ledger, "phone-wrong")
    claim = next(c for c in fact["claims"] if c["id"] == "mom:phone")
    assert state == canonical_claim_state(claim, fact["sources"])


def test_promote_mints_a_fresh_source_when_no_reusable_entry_exists(system: Path) -> None:
    """A hypothesis targeting a fact with no matching sources entry mints one."""
    ledger = system / "ledger"
    (ledger / "facts" / "person").mkdir()
    (ledger / "facts" / "person" / "mom.json").write_text(json.dumps({
        "id": "mom", "type": "person", "name": "Mom", "claims": [],
    }))
    (ledger / "interpretations" / "mom-birthday.json").write_text(json.dumps({
        "id": "mom-birthday", "kind": "hypothesis", "about": ["mom"],
        "statement": "Mom's birthday is in June.", "confidence": "likely",
        "reasoning": "r", "based_on": [f"corpus://{H1}"],
        "proposes": {"id": "mom:birthday", "predicate": "birthday", "value": "June",
                     "evidence": [{"uri": f"corpus://{H1}?el=2", "kind": "authoritative"}]},
        "status": "open", "asof": "2026-07-02",
    }))
    promote(ledger, "mom-birthday")
    fact = json.loads((ledger / "facts" / "person" / "mom.json").read_text())
    birthday = fact["claims"][0]
    skey = birthday["evidence"][0]["source"]
    assert fact["sources"][skey] == {"record": H1}
    assert birthday["evidence"][0]["anchor"] == "el=2"


def test_worklist_directions(system: Path) -> None:
    run_harvest(system / "ledger", _corpora(system))
    rows = worklist(system / "ledger", H1)
    assert any("roster" in r and "chat-14035551234" in r for r in rows)
    assert any(r.startswith("claim") for r in rows)
    (system / "ledger" / "facts" / "person").mkdir()
    (system / "ledger" / "facts" / "person" / "mom.json").write_text(json.dumps({
        "id": "mom", "type": "person", "name": "Mom",
        "sources": {"s1": {"record": H1}},
        "claims": [{"id": "mom:chat", "predicate": "chats_via",
                    "object": "chat-14035551234", "status": "provisional",
                    "asof": "2023-03-01",
                    "evidence": [{"source": "s1", "kind": "direct"}]}],
    }))
    rows = worklist(system / "ledger", "chat-14035551234")
    assert any("mom:chat" in r for r in rows)


def test_coverage_counts(system: Path) -> None:
    run_harvest(system / "ledger", _corpora(system))
    text = render_coverage(system / "ledger", _corpora(system))
    assert "## corpus-private" in text
    assert "2 of 3 records represented" in text  # the group record is backlog
    assert "| `imessage-export` | 3 | 2 |" in text


def test_coverage_counts_claim_evidence_only(system: Path) -> None:
    """A record cited ONLY via claim evidence (no roster entry) still counts
    as represented — a raw-text scan alone would miss it now, since the hash
    is bare under `sources[].record`, never a `corpus://` substring."""
    (system / "ledger" / "facts" / "person").mkdir()
    (system / "ledger" / "facts" / "person" / "mom.json").write_text(json.dumps({
        "id": "mom", "type": "person", "name": "Mom",
        "sources": {"s1": {"record": H1}},
        "claims": [{"id": "mom:greeting", "predicate": "greeting", "value": "x",
                    "status": "provisional", "asof": "2023-03-01",
                    "evidence": [{"source": "s1", "kind": "direct"}]}],
    }))
    assert H1 in represented_hashes(system / "ledger")


def test_coverage_backlog_representation_demand(system: Path) -> None:
    """Each uncovered record's backlog line carries the prescribed work item
    (§9) plus whatever mechanical identification the corpus already has."""
    run_harvest(system / "ledger", _corpora(system))  # H1, H2 roster; H3 (group) stays bare
    text = render_coverage(system / "ledger", _corpora(system))
    assert "### Backlog — representation demand (§9)" in text
    backlog = text.split("### Backlog — representation demand (§9)", 1)[1]
    assert H3[:12] in backlog
    assert H1[:12] not in backlog and H2[:12] not in backlog  # represented, not backlog
    assert ("identify the work this record manifests; stub it if new (§4.2); "
            "roster it with representation fields.") in backlog
    assert "mime `text/html`" in backlog  # the mechanical fact this fixture's records carry


def test_coverage_backlog_member_leaf_labeled_not_host(system: Path) -> None:
    """A promoted member's origin `uri:` is `corpus://<container>?…` — its
    netloc is the container's blake3, not a web host. The backlog line must
    read "member of `<hash>…`", never "host `<hash>`"."""
    _promoted_member_record(system / "corpora" / "corpus-private", H4, H1)
    run_harvest(system / "ledger", _corpora(system))
    text = render_coverage(system / "ledger", _corpora(system))
    backlog = text.split("### Backlog — representation demand (§9)", 1)[1]
    assert H4[:12] in backlog
    assert f"member of `{H1[:12]}…`" in backlog
    assert "host `" not in backlog


def test_coverage_backlog_prefers_latest_origin_over_containment_lineage(
    system: Path,
) -> None:
    """Origin blocks are append-only history (spec/corpus.md §5.2) — after a
    v32 envelope collapse, a promoted member's container may be gone while a
    LATER origin block records its real (live) source, e.g. a web host. The
    frontier label must read the LATEST block, not the first — matching the
    same latest-block-decides principle `dangling_origin_refs` uses — so a
    now-standalone record reads "host `example.com`", never a stale "member
    of" pointing at containment history."""
    _reattributed_member_record(system / "corpora" / "corpus-private", H4, H1)
    run_harvest(system / "ledger", _corpora(system))
    text = render_coverage(system / "ledger", _corpora(system))
    backlog = text.split("### Backlog — representation demand (§9)", 1)[1]
    assert H4[:12] in backlog
    assert "host `example.com`" in backlog
    assert f"member of `{H1[:12]}…`" not in backlog


def test_coverage_no_phantom_row_for_dangling_containment_lineage(system: Path) -> None:
    """A promoted member's ONLY origin block names a container that no
    longer has a record file — the container was `corpus rm`'d, or a v32
    envelope collapse retired it. Coverage must not materialize that dead
    hash as its own covered-table row/group key or a "member of" backlog
    claim (a phantom row for a record with no record file); it groups by
    whatever else the origin carries (`origin.id`) instead, and the
    dangling lineage is surfaced once as a summary note pointing at
    `corpus health`'s `dangling_origin_refs`."""
    H_DEAD_CONTAINER = "5" * 64  # never written as a record — dangling lineage target
    _promoted_member_record(system / "corpora" / "corpus-private", H4, H_DEAD_CONTAINER)
    run_harvest(system / "ledger", _corpora(system))
    text = render_coverage(system / "ledger", _corpora(system))
    assert H_DEAD_CONTAINER not in text  # no phantom row/group keyed by the dead hash
    backlog = text.split("### Backlog — representation demand (§9)", 1)[1]
    assert H4[:12] in backlog
    assert "member of `" not in backlog
    assert ("1 record(s) carry containment lineage into a nonexistent record" in text
            and "dangling_origin_refs" in text)


def test_coverage_reverse_read_rostered_never_cited(system: Path) -> None:
    """§9's reverse read: a concept's rostered manifestation that no claim
    has ever cited is visible per concept — here, H1 is rostered on `mom`
    but never appears in any `sources` table or interpretation."""
    (system / "ledger" / "facts" / "person").mkdir()
    (system / "ledger" / "facts" / "person" / "mom.json").write_text(json.dumps({
        "id": "mom", "type": "person", "name": "Mom",
        "artifacts": [{"uri": f"corpus://{H1}", "role": "documents", "modality": "text"}],
    }))
    text = render_coverage(system / "ledger", _corpora(system))
    assert "## Rostered, never cited" in text
    reverse = text.split("## Rostered, never cited", 1)[1]
    assert "`mom`" in reverse
    assert H1[:12] in reverse
    assert "`documents/text`" in reverse


def test_coverage_reverse_read_excludes_cited_manifestations(system: Path) -> None:
    """A roster entry whose URI IS cited by claim evidence never lands in the
    reverse-read section — only genuinely un-leaned-on entries do."""
    (system / "ledger" / "facts" / "person").mkdir()
    (system / "ledger" / "facts" / "person" / "mom.json").write_text(json.dumps({
        "id": "mom", "type": "person", "name": "Mom",
        "artifacts": [{"uri": f"corpus://{H1}", "role": "documents"}],
        "sources": {"s1": {"record": H1}},
        "claims": [{"id": "mom:greeting", "predicate": "greeting", "value": "x",
                    "status": "provisional", "asof": "2023-03-01",
                    "evidence": [{"source": "s1", "kind": "direct"}]}],
    }))
    text = render_coverage(system / "ledger", _corpora(system))
    reverse = text.split("## Rostered, never cited", 1)[1]
    assert "`mom`" not in reverse


def test_quote_found_requires_document_order() -> None:
    """Fragments must be a FORWARD reading of the record — backward assembly
    of true substrings is refuted (the anti- "Head bolts | 100 ft-lb" rule)."""
    from ledger.verify import _quote_found

    table = ("<tr><td>Head bolts</td><td>22 ft-lb</td></tr>"
             "<tr><td>Wheel lug nuts</td><td>100 ft-lb</td></tr>")
    assert _quote_found("Head bolts | 22 ft-lb", table)
    assert _quote_found("Head bolts ... lug nuts", table)
    assert not _quote_found("100 ft-lb | Head bolts", table)
    assert not _quote_found("lug nuts ... Head bolts", table)


def test_unchecked_anchor_quote_counts_record_scoped(system: Path) -> None:
    """A quote behind an unresolvable anchor (?path=, time_range=) verifies
    against the whole record — counted, so the class can't grow silently."""
    ledger = system / "ledger"
    (ledger / "facts" / "person").mkdir(parents=True, exist_ok=True)
    (ledger / "facts" / "person" / "zip.json").write_text(json.dumps({
        "id": "zip", "type": "person", "name": "Zip",
        "sources": {"s1": {"record": H1}},
        "claims": [{"id": "zip:x", "predicate": "greeting", "value": "x",
                    "status": "provisional", "asof": "2023-03-01",
                    "evidence": [{"source": "s1", "anchor": "path=member.txt",
                                  "quote": "hello from   the fixture",
                                  "kind": "direct"}]}],
    }))
    join = CorpusJoin(_corpora(system))
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1 and res.record_scoped == 1


def test_verify_derived_title_with_no_frontmatter_pair(tmp_path: Path) -> None:
    """Post-3.2 the frontmatter title/description pair is usually absent — the
    display title is DERIVED from a role-marked schema field instead (corpus
    §4.2.3). A quote of that derived title must still verify: the value is
    recomputable from the record's own stored blocks, machine-checkable like
    any attested field (ledger.md §6.3, 1.2), even with no frontmatter pair
    to fall back on. Custom role-marked schema mirrors
    `test_derived_editorial.py`'s synthetic overlays."""
    import yaml

    from corpus import schemas

    h = "5" * 64
    mime = "application/x-test-verify-title"
    root = tmp_path / "corpus"
    schema_dir = root / "schema" / "mime" / "application"
    schema_dir.mkdir(parents=True)
    (schema_dir / "application_x-test-verify-title.yaml").write_text(
        yaml.safe_dump({
            "applies_to": {"content_types": [mime]},
            "extended_fields": {"subject": {"type": "string", "role": "title"}},
        }, sort_keys=False),
        encoding="utf-8",
    )
    p = root / "records" / h[:2] / f"{h}.md"
    p.parent.mkdir(parents=True)
    p.write_text(
        f"---\nid: {h}\ntouch:\n- corpus.ingest@0.1.0\n---\n\n"
        f"<!--artifact {mime}\nsubject: Derived Display Title\n-->\n\n"
        "<!--origin\nsnapshot: '2026-01-01T00:00:00Z'\n-->\n\n"
        "<!--segment text\naddress: el=1\n-->\nbody text\n<!--/segment-->\n",
        encoding="utf-8",
    )
    schemas.cache_clear()

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "thing").mkdir(parents=True)
    (ledger / "facts" / "thing" / "widget.json").write_text(json.dumps({
        "id": "widget", "type": "thing", "name": "Widget",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "widget:title", "predicate": "titled", "value": "x",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "quote": "Derived Display Title",
                                  "kind": "authoritative"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1
    assert not res.errors and not res.warnings


def test_verify_section_header_title_quote(tmp_path: Path) -> None:
    """A form span's header `title:` field (corpus §4.2.3 — the vouch's new
    home) is normalizer-written editorial prose the record body carries; a
    quote against it must verify like any other body content (ledger.md
    §6.3, 1.2). `title:` lives in `Section.extra`, distinct from the
    dataclass's own `.description` field."""
    import frontmatter

    from corpus import paths, records, segments

    h = "6" * 64
    root = tmp_path / "corpus"
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/plain", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    seg = segments.Segment(atom="text", address="turn=1", body="transcript body")
    section = segments.Section(
        address="turn=1-1", form="testform", segments=[seg],
        extra={"title": "Span Header Title"},
    )
    post.content = segments.emit([section])
    records.dump(post, paths.record_path(root, h))

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "thing").mkdir(parents=True)
    (ledger / "facts" / "thing" / "widget.json").write_text(json.dumps({
        "id": "widget", "type": "thing", "name": "Widget",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "widget:title", "predicate": "titled", "value": "x",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "turn=1",
                                  "quote": "Span Header Title",
                                  "kind": "authoritative"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1
    assert not res.errors and not res.warnings


def test_verify_row_axis_falls_back_to_record_scoped(tmp_path: Path) -> None:
    """A CSV row=/col= evidence anchor (corpus §6.2's `row=`/`col=` resolver unit op)
    cites a record whose rows are NEVER stored as segments
    (`row=<N>` is a pure resolver derivation, deliberately not a body address axis) —
    confirming `_parse_axis_values`'s integer-span parsing handles `row=` generically
    (the contact-card arc's precedent for `turn=`/`card=`) exactly like any other
    address the record's markdown doesn't carry: `scoped_text` reports `unchecked`
    (empty `content.spans['row']`, no segments at all), the quote search falls back to
    the whole record, and — since a terminal CSV record's origin block still carries a
    citable `filename:` field — the citation verifies, `record_scoped`, never a hard
    failure and never a crash on the string-valued `col=` companion param."""
    import frontmatter

    from corpus import paths, records

    h = "7" * 64
    root = tmp_path / "corpus"
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/csv", fields={})
    records.append_origin_block(
        post, snapshot="2026-01-01T00:00:00Z", fields={"filename": "trips_data-0.csv"}
    )
    records.dump(post, paths.record_path(root, h))

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "thing").mkdir(parents=True)
    (ledger / "facts" / "thing" / "widget.json").write_text(json.dumps({
        "id": "widget", "type": "thing", "name": "Widget",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "widget:file", "predicate": "sourced-from", "value": "x",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "row=37&col=city_name",
                                  "quote": "trips_data-0.csv",
                                  "kind": "direct"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1 and res.record_scoped == 1
    assert not res.errors and not res.warnings


def test_verify_segments_surface_no_persisted_segments_is_deferred(tmp_path: Path) -> None:
    """§13.2.4 *(1.8)*: a `segments`-surface record (`text/html`, corpus §7.1's
    built-in default) with zero persisted segments is a DEFERRED surface — claim
    evidence citing it is neither failed nor warned: the quote is held unmatched
    (never soup-matched record-wide), the entry counts as `deferred`, the record
    lands in the demand aggregate, and the source is never stamped."""
    import frontmatter

    from corpus import paths, records

    h = "8" * 64
    root = tmp_path / "corpus"
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    records.dump(post, paths.record_path(root, h))

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "thing").mkdir(parents=True)
    fact_path = ledger / "facts" / "thing" / "widget.json"
    fact_path.write_text(json.dumps({
        "id": "widget", "type": "thing", "name": "Widget",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "widget:x", "predicate": "described", "value": "x",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "quote": "anything at all",
                                  "kind": "direct"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=True)
    assert res.verified == 0
    assert res.deferred == 1
    assert res.demand == {h: 1}
    assert not res.errors and not res.warnings
    # held, not stamped: the source must not read as freshly verified
    assert "verified" not in json.loads(fact_path.read_text())["sources"]["s1"]


def test_verify_deferred_surface_byte_fact_quote_still_verifies(tmp_path: Path) -> None:
    """§13.2.4 *(1.8)*: deferral holds only what cannot be checked. A quote that
    lands on the record's attested byte-facts (here an origin `filename:` field —
    a verifiable surface per §6.3) verifies NOW, even though the record's declared
    citation surface has not formed; a second, unfindable quote on the same source
    defers — and the mixed source stays unstamped."""
    import frontmatter

    from corpus import paths, records

    h = "a" * 64
    root = tmp_path / "corpus"
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(
        post, snapshot="2026-01-01T00:00:00Z", fields={"filename": "saved-page.html"}
    )
    records.dump(post, paths.record_path(root, h))

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "thing").mkdir(parents=True)
    (ledger / "facts" / "thing" / "widget.json").write_text(json.dumps({
        "id": "widget", "type": "thing", "name": "Widget",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "widget:x", "predicate": "described", "value": "x",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [
                        {"source": "s1", "quote": "saved-page.html", "kind": "direct"},
                        {"source": "s1", "quote": "not in any byte-fact",
                         "kind": "direct"},
                    ]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1
    assert res.deferred == 1
    assert res.demand == {h: 1}
    assert not res.errors and not res.warnings


def test_verify_segments_surface_with_persisted_segments_verifies(tmp_path: Path) -> None:
    """The same mime, once normalized into a persisted segment, verifies exactly
    like any other formed record — the gate keys to segment presence, never the
    mime alone."""
    import frontmatter

    from corpus import paths, records, segments

    h = "9" * 64
    root = tmp_path / "corpus"
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    seg = segments.Segment(atom="text", address="el=1",
                            body="hello from the rendered surface")
    post.content = segments.emit([seg])
    records.dump(post, paths.record_path(root, h))

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "thing").mkdir(parents=True)
    (ledger / "facts" / "thing" / "widget.json").write_text(json.dumps({
        "id": "widget", "type": "thing", "name": "Widget",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "widget:x", "predicate": "described", "value": "x",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "el=1",
                                  "quote": "hello from the rendered surface",
                                  "kind": "direct"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1
    assert not res.errors and not res.warnings


def test_verify_interpretation_may_reference_segmentless_html_with_enqueue_need(
    tmp_path: Path,
) -> None:
    """§13.2.4 *(1.8)*: interpretations reference deferred surfaces freely — the
    reference joins the demand aggregate (an explicit `enqueue` need may ride
    along, but is no longer policed: the citation is itself the pressure)."""
    import frontmatter

    from corpus import paths, records

    h = "b" * 64
    root = tmp_path / "corpus"
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    records.dump(post, paths.record_path(root, h))

    ledger = tmp_path / "ledger"
    (ledger / "interpretations").mkdir(parents=True)
    (ledger / "facts").mkdir()
    (ledger / "interpretations" / "hunch.json").write_text(json.dumps({
        "id": "hunch", "kind": "hypothesis", "status": "open", "confidence": "low",
        "statement": "the page probably says X", "reasoning": "skimmed the raw capture",
        "based_on": [f"corpus://{h}"],
        "needs": [{"action": "enqueue", "record": f"corpus://{h}", "why": "normalize"}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert not res.errors and not res.warnings
    assert res.demand == {h: 1}


def test_verify_interpretation_reference_without_need_is_clean_demand(
    tmp_path: Path,
) -> None:
    """*(1.8)* The same reference with no typed need draws NOTHING — the 1.4
    needs-warning retired with enqueue-before-cite. The reference simply lands
    in the demand aggregate: cite-then-pressure."""
    import frontmatter

    from corpus import paths, records

    h = "c" * 64
    root = tmp_path / "corpus"
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    records.dump(post, paths.record_path(root, h))

    ledger = tmp_path / "ledger"
    (ledger / "interpretations").mkdir(parents=True)
    (ledger / "facts").mkdir()
    (ledger / "interpretations" / "hunch.json").write_text(json.dumps({
        "id": "hunch", "kind": "hypothesis", "status": "open", "confidence": "low",
        "statement": "the page probably says X", "reasoning": "skimmed the raw capture",
        "based_on": [f"corpus://{h}"],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert not res.errors and not res.warnings
    assert res.demand == {h: 1}


def test_verify_interpretation_proposes_inline_uri_joins_demand(
    tmp_path: Path,
) -> None:
    """corpus:// refs live in two homes on an interpretation: `based_on`, and — for
    a hypothesis's `proposes` — the pre-reforge inline-`uri` evidence shape (check.py's
    PROPOSES_EVIDENCE_KEYS; proposes predates the fact it targets, so it can't yet cite
    a sources-table key). The demand aggregate must catch THIS home too, not just
    `based_on` — the deferred hash here is cited ONLY via `proposes.evidence[].uri`."""
    import frontmatter

    from corpus import paths, records

    h = "d" * 64
    other = "e" * 64  # `based_on`'s own citation — unrelated to the proxy record
    root = tmp_path / "corpus"
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=h, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, snapshot="2026-01-01T00:00:00Z")
    records.dump(post, paths.record_path(root, h))
    other_post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=other, touch_id="corpus.ingest@0.1.0")
    )
    records.set_artifact_block(other_post, mime="text/plain", fields={})
    records.append_origin_block(other_post, snapshot="2026-01-01T00:00:00Z")
    records.dump(other_post, paths.record_path(root, other))

    ledger = tmp_path / "ledger"
    (ledger / "interpretations").mkdir(parents=True)
    (ledger / "facts").mkdir()
    (ledger / "interpretations" / "hunch.json").write_text(json.dumps({
        "id": "hunch", "kind": "hypothesis", "status": "open", "confidence": "low",
        "statement": "the page probably says X", "reasoning": "skimmed the raw capture",
        "based_on": [f"corpus://{other}"],
        "proposes": {
            "id": "widget:x", "predicate": "described", "asof": "2026-01-01",
            "reasoning": "skimmed",
            "evidence": [{"uri": f"corpus://{h}?el=2", "quote": "x", "kind": "direct"}],
        },
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert not res.errors and not res.warnings
    assert res.demand == {h: 1}  # `other` is text/plain — raw surface, no demand


def _ingest_vcard(root: Path, raw: bytes, name: str = "contact.vcf") -> str:
    """Ingest a real `.vcf` artifact (mirrors `test_resolver_vcard_prop.py`'s
    `_ingest`) so `?prop=<N>` resolves against genuine bytes through
    `corpus.resolver.resolve` — a formless record with NO stored segments, so
    `scoped_text` reports `unchecked` and verification must reach the (1.5)
    derived-surface resolution path rather than the record markdown."""
    import shutil

    from corpus import hashing
    from corpus._cli import ingest as ingest_cli

    (root / "records").mkdir(parents=True, exist_ok=True)
    (root / "schema").mkdir(parents=True, exist_ok=True)
    cap = root / "capture"
    cap.mkdir(exist_ok=True, parents=True)
    src = root / name
    src.write_bytes(raw)
    staged = cap / name
    shutil.copy(src, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    rid = hashing.hash_file(src)["blake3"]
    src.unlink()
    return rid


#: property order: 1=VERSION, 2=FN, 3=NOTE. FN's text is duplicated onto the
#: drafter's embed `description:` (the card's display name, corpus §7.1's
#: vcard-manifest strategy) — citable through the EXISTING record-wide
#: fallback, so `?prop=2` alone wouldn't exercise the new resolver path.
#: NOTE carries text found nowhere else in the record's stored markdown —
#: `?prop=3` genuinely requires the (1.5) derived-surface resolution.
_ADA_CARD = (
    b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ada Lovelace\r\n"
    b"NOTE:Pioneer of computing\r\nEND:VCARD\r\n"
)
# a PHOTO-bearing card (property 4) whose property is binary-encoded — the
# resolver's `prop=` transform refuses to render it as text (a clear error,
# never a guessed rendering): the honest "op can't run here" case (1.5)
_PHOTO_CARD = (
    b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:Ada Lovelace\r\n"
    b"NOTE:Pioneer of computing\r\n"
    b"PHOTO;ENCODING=b;TYPE=PNG:"
    b"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M8AAAMBAQDJ"
    b"/pLvAAAAAElFTkSuQmCC\r\n"
    b"END:VCARD\r\n"
)


def test_verify_derived_surface_prop_anchor_resolves_via_resolver(tmp_path: Path) -> None:
    """(1.5) A `?prop=` anchor into a record with NO stored segments — the
    stored markdown can't scope it (`scoped_text` reports `unchecked`) and the
    quote lives nowhere in the record's own body — resolves through the corpus
    resolver as a library call (the same path `corpus resolve` uses) instead of
    being declared unverifiable. `--stamp` additionally earns the source an
    `ops` pin (§13.2, 1.5) keyed off the resolver's own engine-version
    introspection, never hand-written."""
    root = tmp_path / "corpus"
    h = _ingest_vcard(root, _ADA_CARD)

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "person").mkdir(parents=True)
    (ledger / "facts" / "person" / "ada.json").write_text(json.dumps({
        "id": "ada", "type": "person", "name": "Ada",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "ada:note", "predicate": "described", "value": "x",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "prop=3",
                                  "quote": "Pioneer of computing", "kind": "authoritative"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=True, today="2026-07-19")
    assert res.verified == 1 and res.derived_resolved == 1
    assert not res.errors and not res.warnings

    fact = json.loads((ledger / "facts" / "person" / "ada.json").read_text())
    verified = fact["sources"]["s1"]["verified"]
    assert verified["at"] == "2026-07-19"
    assert isinstance(verified["touch"], str)  # a raw ingest stub's `touch:` is a bare
    # scalar, not the list form `load_record_content` reads — "" here is expected and
    # pre-existing, orthogonal to what this test actually probes (the `ops` binding)
    assert verified["ops"] == {"prop": "vcard-prop@1"}

    # unchanged pin (and touch): a later-day re-run must NOT re-stamp
    res2 = verify_ledger(ledger, join, {}, stamp=True, today="2026-07-20")
    assert res2.verified == 1 and res2.stamped == 0
    fact2 = json.loads((ledger / "facts" / "person" / "ada.json").read_text())
    assert fact2["sources"]["s1"]["verified"]["at"] == "2026-07-19"


def test_verify_derived_surface_quote_mismatch_is_a_real_failure(tmp_path: Path) -> None:
    """(1.5) The resolver DOES produce a textual surface, but the cited quote
    isn't in it — a real failure at the claim's status severity, exactly like
    any other quote miss, never a silent unverifiable."""
    root = tmp_path / "corpus"
    h = _ingest_vcard(root, _ADA_CARD)

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "person").mkdir(parents=True)
    (ledger / "facts" / "person" / "ada.json").write_text(json.dumps({
        "id": "ada", "type": "person", "name": "Ada",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "ada:name", "predicate": "named", "value": "x",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "prop=2",
                                  "quote": "Someone Else Entirely",
                                  "kind": "authoritative"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 0 and res.derived_resolved == 0 and res.unverifiable == 0
    assert len(res.errors) == 1  # confirmed status → error severity
    assert "quote not found verbatim in the derived surface" in res.errors[0]


def test_verify_derived_surface_honestly_unverifiable_when_op_cannot_run(
    tmp_path: Path,
) -> None:
    """(1.5) The resolver op genuinely can't run here (a binary vCard property
    the `prop=` transform refuses to render as text — a clear error, never a
    guessed rendering) — the honest `unverifiable` path applies, never a
    failure, and the note carries the resolver's own reason."""
    root = tmp_path / "corpus"
    h = _ingest_vcard(root, _PHOTO_CARD, name="photo.vcf")

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "person").mkdir(parents=True)
    (ledger / "facts" / "person" / "ada.json").write_text(json.dumps({
        "id": "ada", "type": "person", "name": "Ada",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "ada:photo", "predicate": "pictured", "value": "x",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "prop=4",
                                  "quote": "anything", "kind": "incidental"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 0 and res.derived_resolved == 0
    assert res.unverifiable == 1
    assert not res.errors and not res.warnings
    assert any("resolver:" in n and "binary" in n for n in res.notes)


def test_verify_derived_surface_ops_pin_drift_warns(tmp_path: Path) -> None:
    """(1.5) A source's `verified.ops` binding pins the engine current at the
    LAST stamp; when the live engine has since moved (an op-pin upgrade),
    verification — even without --stamp — flags it for re-verification, since
    a passing quote re-check alone can't reveal that the pin itself is stale
    (the resolver always runs the CURRENT engine)."""
    import ledger.verify as verify_mod

    root = tmp_path / "corpus"
    h = _ingest_vcard(root, _ADA_CARD)

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "person").mkdir(parents=True)
    (ledger / "facts" / "person" / "ada.json").write_text(json.dumps({
        "id": "ada", "type": "person", "name": "Ada",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "ada:note", "predicate": "described", "value": "x",
                    "status": "provisional", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "prop=3",
                                  "quote": "Pioneer of computing", "kind": "direct"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    stamp_res = verify_ledger(ledger, join, {}, stamp=True, today="2026-07-19")
    assert stamp_res.stamped == 1

    real_op_engine_map = verify_mod._op_engine_map

    def _upgraded_engine(corpus_root: Path, media_type: str) -> dict[str, str]:
        live = dict(real_op_engine_map(corpus_root, media_type))
        if "prop" in live:
            live["prop"] = "vcard-prop@2"
        return live

    verify_mod._op_engine_map = _upgraded_engine
    try:
        res = verify_ledger(ledger, join, {}, stamp=False)
    finally:
        verify_mod._op_engine_map = real_op_engine_map
    assert any("derivation-op pin drifted" in w for w in res.warnings)
    assert any("vcard-prop@1" in w and "vcard-prop@2" in w for w in res.warnings)


def _ingest_zip(root: Path, members: dict[str, bytes], name: str = "bundle.zip") -> str:
    """Ingest a real `.zip` archive (bare `application/zip`, corpus §7.1's
    zip-manifest strategy) so `?path=<member>` resolves against genuine
    container bytes through `corpus.resolver.resolve`. A bare zip's members
    get no `description` field on their embed (unlike the vcard FN trap
    above), so a citation into a member can ONLY verify through the (1.5)
    derived-surface resolution path — never the record-wide fallback."""
    import shutil
    import zipfile

    from corpus import hashing
    from corpus._cli import ingest as ingest_cli

    (root / "records").mkdir(parents=True, exist_ok=True)
    (root / "schema").mkdir(parents=True, exist_ok=True)
    cap = root / "capture"
    cap.mkdir(parents=True, exist_ok=True)
    zpath = root / name
    with zipfile.ZipFile(zpath, "w") as zf:
        for member_name, data in members.items():
            zf.writestr(member_name, data)
    staged = cap / name
    shutil.copy(zpath, staged)
    assert ingest_cli._ingest_one(root, staged) == 0
    rid = hashing.hash_file(zpath)["blake3"]
    zpath.unlink()
    return rid


def test_verify_derived_surface_path_member_reads_real_file_not_stringified_path(
    tmp_path: Path,
) -> None:
    """(1.5 defect) `corpus.resolver.resolve()` returns a `pathlib.Path` — for a
    large/binary-ish resolver output, a CACHE FILE PATH the caller must read,
    never the text itself. Regression against matching the stringified path by
    accident: the quote here (spaces, punctuation, prose) could never appear in
    a cache file's path string, so it only verifies if the code genuinely reads
    the file's bytes."""
    root = tmp_path / "corpus"
    member_text = "the shipment arrives Tuesday at the north dock, ask for Rosalind"
    h = _ingest_zip(root, {"notes/log.txt": member_text.encode("utf-8")})

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "thing").mkdir(parents=True)
    (ledger / "facts" / "thing" / "widget.json").write_text(json.dumps({
        "id": "widget", "type": "thing", "name": "Widget",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "widget:note", "predicate": "described", "value": "x",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "path=notes/log.txt",
                                  "quote": "arrives Tuesday at the north dock",
                                  "kind": "direct"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1 and res.derived_resolved == 1
    assert not res.errors and not res.warnings


def test_verify_derived_surface_preserves_literal_markup_characters(tmp_path: Path) -> None:
    """(1.5 defect, found live against the real ledger): derived-surface text is
    raw resolver output — a Discord/chat export member, never normalizer-
    authored markdown — so literal `<3`, `>`, `*`, `|` in it must compare
    verbatim, not get stripped as markup. Before the fix, `_norm`'s HTML-tag
    stripping (correct for record markdown, wrong here) treated an unmatched
    `<` (a "<3" heart) as an opening tag and consumed everything up to the
    NEXT unrelated `>` anywhere later in the text — against the real ledger
    this silently deleted a 2 MB span that happened to include the cited
    quote, reporting a real citation as a false failure."""
    root = tmp_path / "corpus"
    member_text = (
        "sold out in <1 min\n"
        "hey <3 Finland\n"
        "> quoting an earlier message\n"
        "dae going to see lynyrd skynyrd tonight\n"
        "ranked: ba > noctis > mdf\n"
    )
    h = _ingest_zip(root, {"chat/log.txt": member_text.encode("utf-8")})

    ledger = tmp_path / "ledger"
    (ledger / "facts" / "thing").mkdir(parents=True)
    (ledger / "facts" / "thing" / "widget.json").write_text(json.dumps({
        "id": "widget", "type": "thing", "name": "Widget",
        "sources": {"s1": {"record": h}},
        "claims": [{"id": "widget:concert", "predicate": "described", "value": "x",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": "path=chat/log.txt",
                                  "quote": "dae going to see lynyrd skynyrd tonight",
                                  "kind": "direct"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.verified == 1 and res.derived_resolved == 1
    assert not res.errors and not res.warnings
