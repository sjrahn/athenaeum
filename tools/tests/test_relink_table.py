"""`corpus relink-table` (#164 → #118's table case) — the surgical data-table link
restoration: the addressed table's anchors come back as `[text](href)`, and NOTHING else in
the record moves."""

from __future__ import annotations

import frontmatter
from bs4 import BeautifulSoup

from corpus import hashing, paths, records, relink_table, schemas
from corpus.store import LocalArtifactStore
from corpus.transforms.html import EL_PARSER_ID, total_element_count

HOST = "my.alldata.com"

_OVERLAY = """\
applies_to:
  host_pattern: my\\.alldata\\.com
"""

_ROWS = [
    ("20-NA-026", "2020/07/22", "Loss of Radio Audio"),
    ("PIC5088F", "2016/04/21", "XM Band Not Receiving All Channels"),
]


def _page() -> str:
    rows = "".join(
        "<tr>"
        f'<td><a href="#/tsb/{n}">{n}</a></td><td>{d}</td>'
        f'<td><a href="#/tsb/{n}">{t}</a></td>'
        "</tr>"
        for n, d, t in _ROWS
    )
    return (
        "<html><body><div>"
        "<table><tr><th>TSB NUMBER</th><th>TSB DATE</th><th>TSB TITLE</th></tr>"
        f"{rows}</table>"
        "</div></body></html>"
    )


def _flat_body() -> str:
    lines = ["| TSB NUMBER | TSB DATE | TSB TITLE |", "| --- | --- | --- |"]
    lines += [f"| {n} | {d} | {t} |" for n, d, t in _ROWS]
    return "\n".join(lines)


def _record(tmp_path, html: str, body: str):
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    overlay_dir = root / "schema" / "origin" / "web"
    overlay_dir.mkdir(parents=True)
    (overlay_dir / f"{HOST}.yaml").write_text(_OVERLAY, encoding="utf-8")
    schemas.cache_clear()

    src = root / "page.html"
    src.write_text(html, encoding="utf-8")
    rid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)

    post = frontmatter.Post(body)
    post.metadata.update({"id": rid, "touch": "corpus.ingest@0.1.0"})
    records.set_artifact_block(
        post,
        mime="text/html",
        fields={
            "addressing": {
                "parser": EL_PARSER_ID,
                "elements": total_element_count(BeautifulSoup(html, EL_PARSER_ID)),
            }
        },
    )
    records.append_origin_block(
        post,
        uri=f"https://{HOST}/repair/#/vehicle/1/component/2/itype/100/tsbs/"
        "isSelfReferenceLink/false",
        snapshot="2026-01-01T00:00:00Z",
        schema_id=HOST,
    )
    record_file = paths.record_path(root, rid)
    records.dump(post, record_file)
    return record_file, root


_SEGMENT = "<!--section index-->\n\n<!--segment text/data-table\naddress: el=1.1\n-->\n\n"


def test_flattened_table_cells_come_back_as_links(tmp_path):
    record_file, root = _record(tmp_path, _page(), _SEGMENT + _flat_body())
    report = relink_table.relink_table_record(record_file, root)
    assert report.hold is None
    assert report.changed is True
    assert report.counts["tables"] == 1
    assert "[20-NA-026](#/tsb/20-NA-026)" in report.new_text
    assert "[Loss of Radio Audio](#/tsb/20-NA-026)" in report.new_text
    # the plain cell stays plain — no anchor in the DOM, no link invented
    assert "| 2020/07/22 |" in report.new_text


def test_only_the_table_segment_body_changes(tmp_path):
    nav = (
        "\n<!--section nav-->\n\n<!--segment text\naddress: el=1\n-->\n\n"
        "[Vehicle](#/v/1) > Radio\n"
    )
    record_file, root = _record(tmp_path, _page(), _SEGMENT + _flat_body() + "\n" + nav)
    report = relink_table.relink_table_record(record_file, root)
    assert report.changed is True
    assert "[Vehicle](#/v/1) > Radio" in report.new_text


def test_a_table_already_linked_is_skipped(tmp_path):
    record_file, root = _record(tmp_path, _page(), _SEGMENT + _flat_body())
    report = relink_table.relink_table_record(record_file, root)
    assert report.changed
    record_file.write_text(report.new_text, encoding="utf-8")
    again = relink_table.relink_table_record(record_file, root)
    assert again.changed is False
    assert again.skipped is not None


def test_a_record_with_no_data_table_segment_is_skipped(tmp_path):
    body = "<!--section index-->\n\n<!--segment text\naddress: el=1.1\n-->\n\nplain text\n"
    record_file, root = _record(tmp_path, _page(), body)
    report = relink_table.relink_table_record(record_file, root)
    assert report.skipped == "no addressed text/data-table segment"


def test_an_address_that_is_not_a_table_is_left_alone(tmp_path):
    # el=1 names the wrapping <div>, not the <table> — not this verb's to touch
    body = "<!--section index-->\n\n<!--segment text/data-table\naddress: el=1\n-->\n\nx\n"
    record_file, root = _record(tmp_path, _page(), body)
    report = relink_table.relink_table_record(record_file, root)
    assert report.changed is False
    assert report.skipped is not None


def test_a_body_carrying_prose_beyond_its_table_is_held(tmp_path):
    """The sweep's hard lesson: replacing an over-stuffed body deletes the prose, and the
    gates BLESS the deletion — the dropped lines were the ones failing fidelity under the
    table's address, so the finding vanishes with the content. The verb must refuse."""
    body = _SEGMENT + _flat_body() + "\n\nSupersession Statement\n\nThis PI was superseded.\n"
    record_file, root = _record(tmp_path, _page(), body)
    report = relink_table.relink_table_record(record_file, root)
    assert report.changed is False
    assert report.hold is not None
    assert "not a pure pipe table" in report.hold


def test_a_raw_html_table_body_is_held(tmp_path):
    """A raw `<table>` body may hold colspan/rowspan structure a pipe table cannot express —
    converting it is a degrade, not a link repair."""
    body = _SEGMENT + "<table><tr><td colspan=\"2\">Wide</td></tr></table>\n"
    record_file, root = _record(tmp_path, _page(), body)
    report = relink_table.relink_table_record(record_file, root)
    assert report.changed is False
    assert report.hold is not None
    assert "not a pure pipe table" in report.hold
