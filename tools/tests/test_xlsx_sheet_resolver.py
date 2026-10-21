"""Spreadsheet `sheet=<name>` (+ `bbox=<A1-range>`) resolution (spec §6.2, §12.11) and the
xlsx drafter's banded, unpadded, blank-header body.

The invariant that matters: the drafted body and the resolved cell range are two readings
of the SAME cells (`transforms.xlsx.cell_text`), so a quote taken from one verifies against
the other — and `ath ledger verify` now resolves a `sheet=…&bbox=…` anchor, so a quote the
cells do not hold fails instead of staying unverifiable.
"""

from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

import frontmatter
import pytest

from corpus import functional_uri, hashing, paths, records, resolver, schemas, textnorm
from corpus import mime as mime_mod
from corpus import segments as seg_mod
from corpus._cli import dispatch
from corpus.store import LocalArtifactStore

openpyxl = pytest.importorskip("openpyxl")

_XLSX = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_BIG = "Solar Inverters & Co"  # `&` exercises the %26 address encoding
_N_DATA = 2300  # > 2 bands of 1000


def _workbook(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = _BIG
    ws["A1"] = "Inverter list (title row, not a header)"
    ws["A2"] = "Last updated"
    ws["B2"] = dt.date(2026, 10, 1)
    # rows 3-4 blank; a two-row header at 5-6 with an in-cell newline
    ws.append([])
    ws["A5"] = "Manufacturer"
    ws["B5"] = "Model"
    ws["C5"] = "UL 1741 SA\nFreq-Watt\nVolt-Watt"
    ws["D5"] = "Efficiency"
    ws["A6"] = "Name"
    ws["D6"] = "%"
    for i in range(_N_DATA):
        r = 7 + i
        ws.cell(row=r, column=1, value=f"Maker {i}")
        ws.cell(row=r, column=2, value=f"M-{i:04d} | pipe")
        ws.cell(row=r, column=3, value=(i % 2 == 0))
        ws.cell(row=r, column=4, value=96.5 + (i % 3) / 10)
    small = wb.create_sheet("Small")
    small["B3"] = "only"  # leading blank rows AND a blank column A
    small["C4"] = 7
    from openpyxl.chart import BarChart, Reference

    chart = BarChart()
    chart.add_data(Reference(small, min_col=3, min_row=4, max_row=4))
    wb.create_chartsheet("Chart").add_chart(chart)
    wb.save(path)


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir(parents=True)
    schemas.cache_clear()
    return root


def _stage(root: Path, src: Path) -> str:
    rid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(rid, mime_mod.extension_for(_XLSX), src)
    post = frontmatter.Post("")
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"))
    records.set_artifact_block(post, mime=_XLSX, fields={})
    records.append_origin_block(
        post, snapshot="2026-10-21T00:00:00Z", fields={"filename": src.name, "source_modified": ""}
    )
    records.dump(post, paths.record_path(root, rid))
    return rid


@pytest.fixture(scope="module")
def book(tmp_path_factory) -> Path:
    p = tmp_path_factory.mktemp("xlsx") / "inverters.xlsx"
    _workbook(p)
    return p


def _resolve_text(root: Path, rid: str, address: str) -> str:
    return resolver.resolve(f"corpus://{rid}?{address}", root).read_text(encoding="utf-8")


def _addr(sheet: str, bbox: str | None = None) -> str:
    a = f"sheet={functional_uri.quote_value(sheet)}"
    return a if bbox is None else f"{a}&bbox={bbox}"


# ---------- the resolver ---------- #


def test_bbox_reads_the_exact_rectangle(tmp_path, book):
    root = _corpus(tmp_path)
    rid = _stage(root, book)
    text = _resolve_text(root, rid, _addr(_BIG, "A5:D7"))
    assert text.split("\n") == [
        "Manufacturer\tModel\tUL 1741 SA",  # the in-cell newlines are the cell's own text
        "Freq-Watt",
        "Volt-Watt\tEfficiency",
        "Name\t\t\t%",
        "Maker 0\tM-0000 | pipe\tTRUE\t96.5",
    ]
    # past the band boundary and deep in the sheet — the rows the 1000-row cap used to drop
    deep = _resolve_text(root, rid, _addr(_BIG, "A1840:D1840"))
    assert deep == "Maker 1833\tM-1833 | pipe\tFALSE\t96.5"
    # Excel stores a date as a datetime; the reading is its ISO form
    assert _resolve_text(root, rid, _addr(_BIG, "B2")) == "2026-10-01T00:00:00"


def test_bare_sheet_reads_the_used_range(tmp_path, book):
    root = _corpus(tmp_path)
    rid = _stage(root, book)
    assert _resolve_text(root, rid, _addr("Small")).split("\n") == [
        "\t\t", "\t\t", "\tonly\t", "\t\t7",
    ]


def test_crop_is_an_alias_and_a_range_past_the_data_keeps_its_shape(tmp_path, book):
    root = _corpus(tmp_path)
    rid = _stage(root, book)
    assert _resolve_text(root, rid, _addr("Small", "B3:C4")) == \
        _resolve_text(root, rid, "sheet=Small&crop=B3:C4")
    assert _resolve_text(root, rid, _addr("Small", "C4:D6")) == "7\t\n\t\n\t"


@pytest.mark.parametrize(
    ("address", "needle"),
    [
        ("sheet=Nope", "no such worksheet"),
        ("sheet=Chart", "chart sheet"),
        ("sheet=Small&bbox=0.1,0.1,0.5,0.5", "not an A1 cell reference"),
        ("sheet=Small&bbox=C4:B3", "above and left"),
        ("sheet=Small&bbox=A:C", "not an A1 cell reference"),
        ("bbox=A1:B2", "not applicable"),
    ],
)
def test_bad_addresses_fail_loudly(tmp_path, book, address, needle):
    root = _corpus(tmp_path)
    rid = _stage(root, book)
    with pytest.raises(Exception, match=needle):
        resolver.resolve(f"corpus://{rid}?{address}", root)


def test_engine_pin_rides_sheet_not_the_polymorphic_bbox(tmp_path):
    from corpus.transforms import xlsx as xlsx_tf

    root = _corpus(tmp_path)
    pins = {op.param: op.engine_version for op in resolver.ops_for_media_type(root, _XLSX)}
    assert pins["sheet"] == xlsx_tf.ENGINE_VERSION
    assert pins["bbox"] is None
    assert resolver.engine_version_for_param("bbox") is None  # image crops stay unpinned


# ---------- the drafter ---------- #


def _draft(root: Path, rid: str) -> list:
    from tests._draftlib import draft_for_test

    assert draft_for_test(root, rid) == 0
    assert dispatch(["lint", rid, "--corpus-root", str(root)]) == 0
    post = records.load(paths.record_path(root, rid))
    return [b for b in seg_mod.iter_blocks(post.content) if not b.is_structural]


def test_long_sheet_drafts_whole_as_bands_with_real_row_numbers(tmp_path, book):
    root = _corpus(tmp_path)
    rid = _stage(root, book)
    segs = [s for s in _draft(root, rid) if s.address.startswith(_addr(_BIG))]
    last = 6 + _N_DATA
    assert [s.address for s in segs] == [
        _addr(_BIG, "A1:D1000"), _addr(_BIG, "A1001:D2000"), _addr(_BIG, f"A2001:D{last}"),
    ]
    post = records.load(paths.record_path(root, rid))
    assert not [i for i in records.iter_issue_blocks(post) if "truncated" in str(i)]
    body = segs[0].body
    header, sep, first = body.split("\n")[:3]
    assert header == "|  |  |  |  |"  # blank: no guessed header, no "Col B" filler
    assert sep == "| --- | --- | --- | --- |"
    assert first == "| Inverter list (title row, not a header) |  |  |  |"  # unpadded
    assert "| UL 1741 SA<br>Freq-Watt<br>Volt-Watt |" in body


def test_short_sheet_keeps_the_bare_address(tmp_path, book):
    root = _corpus(tmp_path)
    rid = _stage(root, book)
    small = [s for s in _draft(root, rid) if s.address.startswith("sheet=Small")]
    assert [s.address for s in small] == ["sheet=Small"]
    # leading blank rows skipped; the blank column A kept (it is inside the used range)
    assert small[0].body.split("\n")[2:] == ["|  | only |  |", "|  |  | 7 |"]


def test_every_drafted_row_verifies_against_its_resolved_band(tmp_path, book):
    """The two-surface invariant: each band's resolved range holds every row of its drafted
    body, in order, under the verifier's own comparison."""
    root = _corpus(tmp_path)
    rid = _stage(root, book)
    for seg in _draft(root, rid):
        if not seg.body:
            continue
        resolved = _resolve_text(root, rid, seg.address)
        for line in seg.body.split("\n")[2:]:
            cells = [c.strip() for c in line.strip("|").split(" | ")]
            cells = [c for c in cells if c]
            if not cells:
                continue
            # a row quoted cell-by-cell, as a scribe would; markdown escapes undone
            quote = " | ".join(c.replace("\\|", "|").replace("<br>", "\n") for c in cells)
            assert textnorm.quote_found(quote, resolved, strip_markup=False), (seg.address, quote)
            assert textnorm.quote_found(quote, seg.body), (seg.address, quote)


# ---------- the ledger gate ---------- #


def _fact(ledger: Path, rid: str, anchor: str, quote: str) -> None:
    (ledger / "facts" / "device").mkdir(parents=True, exist_ok=True)
    (ledger / "facts" / "device" / "d.json").write_text(json.dumps({
        "id": "d", "type": "device", "name": "D",
        "sources": {"s1": {"record": rid}},
        "claims": [{"id": "d:x", "predicate": "says", "value": "x",
                    "status": "confirmed", "asof": "2026-01-01",
                    "evidence": [{"source": "s1", "anchor": anchor, "quote": quote,
                                  "kind": "authoritative"}]}],
    }))


@pytest.mark.parametrize(
    ("quote", "ok"),
    [("Maker 1833 | M-1833 | pipe | FALSE | 96.5", True), ("Maker 9999 | 12.0", False)],
)
def test_verify_resolves_a_cell_range_anchor_on_an_unformed_record(tmp_path, book, quote, ok):
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    root = _corpus(tmp_path)
    rid = _stage(root, book)  # never drafted: no stored segment holds these cells
    ledger = root.parent / "ledger"
    _fact(ledger, rid, _addr(_BIG, "A1840:D1840"), quote)
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.unverifiable == 0, res.notes
    if ok:
        assert not res.errors and res.verified == 1 and res.derived_resolved == 1
    else:
        assert res.verified == 0 and len(res.errors) == 1
        assert "quote not found verbatim in the derived surface" in res.errors[0]


@pytest.mark.parametrize(
    ("quote", "ok"),
    # "Maker 1833" is on the record (row 1840's band body) — but not at A1841
    [("Maker 1834", True), ("Maker 1833", False)],
)
def test_verify_checks_a_cell_anchor_on_a_drafted_record_at_the_cell(tmp_path, book, quote, ok):
    """A drafted record's stored segments are bands; a single-cell anchor inside one is
    finer than any stored address, so it resolves through the resolver — never passes on
    a record-wide match of a quote that sits in some other row (ledger §13.2.3)."""
    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger

    root = _corpus(tmp_path)
    rid = _stage(root, book)
    _draft(root, rid)
    ledger = root.parent / "ledger"
    _fact(ledger, rid, _addr(_BIG, "A1841:A1841"), quote)
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False)
    assert res.unverifiable == 0 and res.record_scoped == 0, res.notes
    if ok:
        assert not res.errors and res.verified == 1 and res.derived_resolved == 1
    else:
        assert res.verified == 0 and len(res.errors) == 1
        assert "derived surface" in res.errors[0]
