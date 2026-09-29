"""`corpus triage` (spec §8.5, v50): read-only packets for the form-triage agent.

It may run over the requested records (the only ones a hint may join) or, as a report, over
the whole proxy population — and in neither scope does it write a record or enqueue one.
"""

from __future__ import annotations

import json
from pathlib import Path

import frontmatter

from corpus import paths, queue, records, schemas, segments, triage
from corpus._cli import dispatch

A, B, C = "a" * 64, "b" * 64, "c" * 64


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _put(root: Path, rid: str, *, blocks: list | None = None) -> Path:
    post = frontmatter.Post(
        segments.emit(blocks or []),
        **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"),
    )
    records.set_artifact_block(post, mime="text/plain", fields={"title": f"Doc {rid[:1]}"})
    records.append_origin_block(post, uri=f"file:///{rid[:1]}.txt", snapshot="2026-09-28T00:00:00Z")
    p = paths.record_path(root, rid)
    records.dump(post, p)
    return p


def _run(root: Path, *args: str, capsys) -> list[dict]:
    assert dispatch(["triage", *args, "--corpus-root", str(root)]) == 0
    return [json.loads(ln) for ln in capsys.readouterr().out.splitlines() if ln.strip()]


def test_the_default_scope_is_the_requested_formless_records(tmp_path, capsys):
    root = _corpus(tmp_path)
    for rid in (A, B):
        _put(root, rid)
    _put(root, C, blocks=[segments.Section(form="document", segments=[
        segments.Segment(atom="text", address=None, body="Formed already.")])])
    queue.enqueue(root, A)
    queue.enqueue(root, C)  # requested, but already formed — nothing to propose
    got = _run(root, capsys=capsys)
    assert [p["id"] for p in got] == [A]
    assert got[0]["mime"] == "text/plain" and got[0]["fields"]["title"] == "Doc a"


def test_all_is_a_report_over_the_proxy_population(tmp_path, capsys):
    root = _corpus(tmp_path)
    for rid in (A, B):
        _put(root, rid)
    _put(root, C, blocks=[segments.Segment(atom="text", address=None, body="Rendered whole.")])
    before = {p: p.read_bytes() for p in (root / "records").rglob("*.md")}
    got = _run(root, "--all", capsys=capsys)
    assert sorted(p["id"] for p in got) == [A, B]  # C stores a rendering: not proxy
    # read-only: no record touched, nothing enqueued
    assert {p: p.read_bytes() for p in (root / "records").rglob("*.md")} == before
    assert queue.entries(root) == []


def test_a_governed_record_is_never_triaged(tmp_path):
    root = _corpus(tmp_path)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "bank.yaml").write_text("form: {id: statement}\n", encoding="utf-8")
    schemas.cache_clear()
    post = frontmatter.Post("", **records.stub_frontmatter(record_id=A, touch_id="t@1"))
    records.set_artifact_block(post, mime="application/pdf")
    records.append_origin_block(post, uri="file:///s.pdf", snapshot="2026-09-28T00:00:00Z",
                                schema_id="bank")
    assert not triage.eligible(post, root, proxy_only=True)


def test_the_form_catalog_lists_the_packaged_forms(tmp_path, capsys):
    root = _corpus(tmp_path)
    forms = {row["form"]: row for row in _run(root, "--forms", capsys=capsys)}
    assert {"document", "statement", "passthrough"} <= set(forms)
    assert forms["passthrough"]["terminal"] is True
    assert forms["statement"]["terminal"] is False and forms["statement"]["description"]


def test_a_packet_carries_the_opening_text_when_the_bytes_are_local(tmp_path, monkeypatch):
    import corpus.containment as containment

    root = _corpus(tmp_path)
    src = tmp_path / "a.txt"
    src.write_text("Statement period Aug 1 - Aug 31\n  Opening balance   $10.00\n", "utf-8")
    monkeypatch.setattr(containment, "ensure_local_bytes", lambda *a, **k: src)
    pk = triage.packet(records.load(_put(root, A)), root)
    assert pk["text"] == "Statement period Aug 1 - Aug 31 Opening balance $10.00"


def test_field_rows_count_label_value_rows_however_the_page_builds_them(tmp_path):
    """The triager read "no tables" on myRealPage listings whose facts are `<dl>`s — so the
    packet counts label/value rows, not `<table>` tags."""
    from bs4 import BeautifulSoup

    def rows(html: str) -> int:
        return triage._field_rows(BeautifulSoup(html, "html.parser"))

    dl = "".join(f"<dl><dt>Field {i}:</dt><dd>Value {i}</dd></dl>" for i in range(4))
    assert rows(f"<div>{dl}</div>") == 4  # one per pair, never again as a div-built run
    assert rows("<table><tr><th>Colour</th><td>Grey</td></tr>"
                "<tr><th>Shape</th><td>Rectangle</td></tr></table>") == 2
    # an unclosed row nests the value cell under its header cell
    assert rows("<table><tr><th> Lid Type <td>Manual<tr><th> Colour <td>Grey</table>") == 2
    div = "".join(f"<div><span>Label {i}</span><span>Value {i}</span></div>" for i in range(3))
    assert rows(f"<section>{div}</section>") == 3
    assert rows(f"<section>{div[:len(div) * 2 // 3]}</section>") == 0  # two siblings are no run
    # prose, a header row, and a link list are not fields
    assert rows("<article><p>One paragraph.</p><p>Another.</p></article>") == 0
    assert rows("<table><tr><th>A</th><th>B</th><th>C</th></tr></table>") == 0
    assert rows("<ul><li><a href='/a'>A</a></li><li><a href='/b'>B</a></li></ul>") == 0
