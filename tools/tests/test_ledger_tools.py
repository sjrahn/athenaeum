"""The ledger's deterministic tooling: harvest (§10), evidence verification
(§13.2), promote/stamp (§7.2, §7.3), worklist, coverage."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from ledger.corpora import CorpusJoin, RegisteredCorpus
from ledger.coverage import render_coverage, represented_hashes
from ledger.harvest import HarvestError, load_rules, run_harvest
from ledger.model import canonical_claim_state, derived_uri
from ledger.promote import PromoteError, promote, stamp
from ledger.verify import verify_ledger
from ledger.worklist import worklist

H1 = "1" * 64
H2 = "2" * 64
H3 = "3" * 64


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
    res = verify_ledger(ledger, join, set(), stamp=True, today="2026-07-02")
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
    res2 = verify_ledger(ledger, join, set(), stamp=True, today="2026-07-03")
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
    res = verify_ledger(ledger, join, set(), stamp=True, today="2026-07-02")
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
    res = verify_ledger(ledger, join, set(), stamp=False)
    assert res.verified == 2
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
    res = verify_ledger(ledger, join, set(), stamp=False)
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
    res = verify_ledger(ledger, join, set(), stamp=False)
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
    res = verify_ledger(ledger, join, set(), stamp=False)
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
    res = verify_ledger(ledger, join, set(), stamp=False)
    assert res.verified == 1 and res.record_scoped == 1
    assert not res.errors and not res.warnings
