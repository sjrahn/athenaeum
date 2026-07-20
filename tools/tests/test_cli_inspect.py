"""`corpus inspect` — the one-stop card: identity, artifact, origins, content axes,
resolver ops (see `corpus._cli.inspect_`).

Covers: a full card on a formed (shaped) conversation fixture, the content-axes
compression (dense range vs sparse), resolver-op enumeration for csv/vcard/pdf including
engine pins, no-pipeline mime honesty, prefix resolution, and every-section-prints-honestly
on an empty/bare record.
"""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import frontmatter

from corpus import hashing, paths, records, resolver, schemas, segments
from corpus import mime as mime_mod
from corpus import shape as shape_pkg
from corpus._cli import dispatch
from corpus._cli import inspect_ as inspect_cli
from corpus.store import LocalArtifactStore

# ---------- shared staging helpers ---------- #


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()
    return root


def _stage(
    root: Path,
    data: bytes,
    *,
    mime: str | None,
    name: str,
    content: str = "",
    with_origin: bool = True,
    embeds: list[dict] | None = None,
) -> str:
    """Stage a standalone record directly (bypassing capture/ingest — the fixture asserts
    `inspect` against the record shape directly, like `test_csv_transform.py`'s
    `_stage_record`)."""
    src = root.parent / name
    src.write_bytes(data)
    rid = hashing.hash_file(src)["blake3"]
    if mime is not None:
        ext = mime_mod.extension_for(mime)
        LocalArtifactStore(root).put(rid, ext, src)
    post = frontmatter.Post(content)
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"))
    if mime is not None:
        records.set_artifact_block(post, mime=mime, fields={})
    if with_origin:
        records.append_origin_block(
            post, snapshot="2026-07-18T00:00:00Z", fields={"filename": name}
        )
    for emb in embeds or []:
        records.append_embed_block(post, **emb)
    records.dump(post, paths.record_path(root, rid))
    return rid


# ---------- full card on a formed (shaped) fixture ---------- #

_OVERLAY = """\
applies_to:
  schemes: [convexport]
kind: interpretive
form:
  id: conversation
  mapping:
    messages: messages
    message_id: id
    author_id: author.id
    author_name: author.name
    timestamp: timestamp
    text: content
"""

_CHAT = {
    "messages": [
        {"id": "m1", "author": {"id": "u1", "name": "Andy"},
         "timestamp": "2014-03-04T00:09:34Z", "content": "Yo"},
        {"id": "m2", "author": {"id": "u2", "name": "Steven"},
         "timestamp": "2014-03-04T00:11:02Z", "content": "hey"},
        {"id": "m3", "author": {"id": "u1", "name": "Andy"},
         "timestamp": "2014-03-04T00:12:00Z", "content": "back"},
    ]
}


def _stage_shaped_conversation(tmp_path: Path) -> tuple[Path, str]:
    root = _corpus(tmp_path)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "conv-export.yaml").write_text(_OVERLAY, encoding="utf-8")
    schemas.cache_clear()

    raw = json.dumps(_CHAT).encode()
    src = root / "chat.json"
    src.write_bytes(raw)
    rid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(rid, "json", src)
    src.unlink()

    post = frontmatter.Post("")
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"))
    records.set_artifact_block(post, mime="application/json", fields={})
    records.append_origin_block(
        post, uri=None, snapshot="2026-01-01T00:00:00Z",
        schema_id="conv-export", fields={"filename": "chat.json"},
    )
    rf = paths.record_path(root, rid)
    records.dump(post, rf)
    post = records.load(rf)
    assert shape_pkg.shape_record(post, root) is True
    records.dump(post, rf)
    return root, rid


def test_inspect_full_card_on_formed_fixture(tmp_path, capsys):
    root, rid = _stage_shaped_conversation(tmp_path)
    rc = dispatch(["inspect", rid, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out

    assert f"record:      {rid}" in out
    assert "state:       formed" in out
    assert "governing:   conversation — rendering contract  (declared: origin 'conv-export')" in out
    # raw-class (application/json is not HTML) with 3 persisted segments — citable, and
    # the segment count appends to the raw-surface line.
    assert "citable:     yes (raw surface — record-wide quotes are honest; segments: 3)" in out
    assert "mime:        application/json" in out
    assert "== origins (1) ==" in out
    assert "[conv-export]" in out
    assert "sections:    1 section(s), 3 segment(s)" in out
    assert "axes:        turn=1-3 (3 segments)" in out
    assert "embeds:      none" in out
    # No `working_kind:` schema entry for application/json — honest, not silent.
    assert "mime pipeline: none registered for media_type 'application/json'" in out
    # The record-level unit ops (§6.2) — available because the origin overlay declares
    # a form mapping, independent of the (absent) mime pipeline.
    assert (
        "record-level: body -> markdown · members -> json (0 embed(s)) · "
        "turn=<N> -> json  (form: conversation) [engine: units-turn@1] · "
        "turn=<N>&att=<M> -> bytes  (lineage-chained) [engine: units-turn@1]"
    ) in out


_CARD_OVERLAY = """\
applies_to:
  schemes: [cardexport]
kind: interpretive
form:
  id: contact-card
"""


def test_inspect_no_mapping_form_omits_turn_ops(tmp_path, capsys):
    """A bare `form: {id}` declaration with no mapping (contact-card) has no unit grammar —
    `?turn=` would fail on such a record, so the card must not advertise it."""
    root = _corpus(tmp_path)
    odir = root / "schema" / "origin"
    odir.mkdir(parents=True)
    (odir / "card-export.yaml").write_text(_CARD_OVERLAY, encoding="utf-8")
    schemas.cache_clear()

    raw = b"BEGIN:VCARD\r\nVERSION:3.0\r\nFN:A Person\r\nEND:VCARD\r\n"
    src = root / "card.vcf"
    src.write_bytes(raw)
    rid = hashing.hash_file(src)["blake3"]
    LocalArtifactStore(root).put(rid, mime_mod.extension_for("text/vcard"), src)
    src.unlink()

    post = frontmatter.Post("")
    post.metadata.update(records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0"))
    records.set_artifact_block(post, mime="text/vcard", fields={})
    records.append_origin_block(
        post, uri=None, snapshot="2026-01-01T00:00:00Z",
        schema_id="card-export", fields={"filename": "card.vcf"},
    )
    records.dump(post, paths.record_path(root, rid))

    rc = dispatch(["inspect", rid, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "turn=<N>" not in out
    assert "record-level: body -> markdown · members -> json (0 embed(s))" in out


# ---------- citability line (§7.1 `citation_surface:`) ---------- #


def test_inspect_citable_no_for_proxy_html_record(tmp_path, capsys):
    """A segments-class record (HTML, built-in default) with zero persisted segments is
    not citable — the honest demand is enqueue, never a record-wide quote (§7.1, §8.5)."""
    root = _corpus(tmp_path)
    rid = _stage(root, b"<html><body>hi</body></html>", mime="text/html", name="page.html")
    rc = dispatch(["inspect", rid, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert (
        "citable:     no — segments required, none persisted "
        "(enqueue for normalize; ledger.md §13.2)"
    ) in out


def test_inspect_citable_yes_for_rendered_html_record(tmp_path, capsys):
    """Once an HTML (segments-class) record carries persisted segments, it is citable —
    citability keys to verifiable surfaces, never record state."""
    root = _corpus(tmp_path)
    seg = segments.Segment(atom="text", address="el=1", body="hi there")
    rid = _stage(
        root, b"<html><body>hi</body></html>", mime="text/html", name="page2.html",
        content=segments.emit([seg]),
    )
    rc = dispatch(["inspect", rid, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "citable:     yes (segments: 1)" in out


def test_inspect_citable_yes_for_raw_class_record(tmp_path, capsys):
    """A `raw`-class record (the built-in default for non-HTML types, e.g. CSV) is
    citable even with zero persisted segments — its derived body is already faithful
    line-of-sight content, so record-wide quotes are honest."""
    root = _corpus(tmp_path)
    rid = _stage(root, b"city,fare\r\nCalgary,11\r\n", mime="text/csv", name="fares.csv")
    rc = dispatch(["inspect", rid, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "citable:     yes (raw surface — record-wide quotes are honest)" in out


# ---------- content-axes compression: dense range vs sparse ---------- #


def test_axis_summary_dense_range():
    blocks = [
        segments.Segment(atom="text", address="turn=1", body="a"),
        segments.Segment(atom="text", address="turn=2", body="b"),
        segments.Segment(atom="text", address="turn=3", body="c"),
    ]
    assert inspect_cli._axis_summary(blocks) == ["turn=1-3 (3 segments)"]


def test_axis_summary_single_point_singular_noun():
    blocks = [segments.Segment(atom="text", address="turn=1", body="a")]
    assert inspect_cli._axis_summary(blocks) == ["turn=1 (1 segment)"]


def test_axis_summary_sparse_gap():
    # Only 2 of the 5 slots in [1, 5] are occupied — not a contiguous range.
    blocks = [
        segments.Segment(atom="text", address="turn=1", body="a"),
        segments.Segment(atom="text", address="turn=5", body="b"),
    ]
    assert inspect_cli._axis_summary(blocks) == ["turn sparse (2)"]


def test_axis_summary_sparse_repeat():
    # Two segments addressing the SAME point — count exceeds the (degenerate) span.
    blocks = [
        segments.Segment(atom="text", address="turn=2&att=1", body="a"),
        segments.Segment(atom="text", address="turn=2&att=1", body="b"),
    ]
    lines = inspect_cli._axis_summary(blocks)
    assert "att sparse (2)" in lines


def test_axis_summary_multiple_axes_sorted():
    blocks = [
        segments.Segment(atom="text", address="turn=1&att=1", body="a"),
        segments.Segment(atom="text", address="turn=2", body="b"),
    ]
    # Sorted alphabetically: att before turn.
    assert inspect_cli._axis_summary(blocks) == ["att=1 (1 segment)", "turn=1-2 (2 segments)"]


def test_axis_summary_empty_blocks_is_empty_list():
    assert inspect_cli._axis_summary([]) == []


# ---------- resolver.ops_for_media_type: engine pins, promotion, no-pipeline ---------- #


def test_ops_for_media_type_csv_pins_engine_on_row_and_col(tmp_path):
    root = _corpus(tmp_path)
    ops = {op.param: op for op in resolver.ops_for_media_type(root, "text/csv")}
    assert ops["row"].from_kind == "csv"
    assert ops["row"].output_kind == "csvrow"
    assert ops["row"].engine_version == "csv-row-col@1"
    assert ops["col"].from_kind == "csvrow"
    assert ops["col"].output_kind == "text"
    assert ops["col"].engine_version == "csv-row-col@1"


def test_ops_for_media_type_vcard_pins_engine_on_card_and_prop(tmp_path):
    root = _corpus(tmp_path)
    ops = {op.param: op for op in resolver.ops_for_media_type(root, "text/vcard")}
    assert ops["card"].from_kind == "vcard"
    assert ops["card"].output_kind == "bytes"
    assert ops["card"].engine_version == "vcard-card@1"
    assert ops["prop"].from_kind == "vcard"
    assert ops["prop"].output_kind == "text"
    assert ops["prop"].engine_version == "vcard-prop@1"
    # Independently versioned — a `prop=` semantics change never bumps `card=`'s id or vice versa.
    assert ops["card"].engine_version != ops["prop"].engine_version


def test_ops_for_media_type_mbox_pins_engine_on_msg(tmp_path):
    root = _corpus(tmp_path)
    ops = {op.param: op for op in resolver.ops_for_media_type(root, "application/mbox")}
    assert ops["msg"].from_kind == "mbox"
    assert ops["msg"].output_kind == "bytes"
    assert ops["msg"].engine_version == "mbox-msg@1"


def test_ops_for_media_type_zip_and_tar_pin_the_same_engine_on_path(tmp_path):
    root = _corpus(tmp_path)
    zip_ops = {op.param: op for op in resolver.ops_for_media_type(root, "application/zip")}
    tar_ops = {op.param: op for op in resolver.ops_for_media_type(root, "application/x-tar")}
    assert zip_ops["path"].engine_version == "archive-path@1"
    assert tar_ops["path"].engine_version == "archive-path@1"
    # One canonical id shared verbatim between zip and tar (spec §12.11 `path=`).
    assert zip_ops["path"].engine_version == tar_ops["path"].engine_version


def test_ops_for_media_type_html_pins_engine_on_el(tmp_path):
    root = _corpus(tmp_path)
    ops = {op.param: op for op in resolver.ops_for_media_type(root, "text/html")}
    assert ops["el"].from_kind == "html"
    assert ops["el"].output_kind == "htmlel"
    assert ops["el"].engine_version == "html-el@1"
    # `selector=` is a distinct back-compat op, never pinned by the `el=` id.
    assert ops["selector"].engine_version is None


def test_engine_version_for_param_covers_turn_and_att_off_registry(tmp_path):
    """`turn=`/`att=` are record-level ops (`resolver._resolve_turn`) that bypass
    `transforms.REGISTRY` entirely, so `ops_for_media_type` can never surface them (its walk
    starts from a media type's registry-declared pipeline, and turn= availability depends on
    the record's ORIGIN-declared form mapping instead) — `engine_version_for_param` is the
    direct lookup a caller (this CLI's record-level printer, a future ledger stamp) uses."""
    assert resolver.engine_version_for_param("turn") == "units-turn@1"
    assert resolver.engine_version_for_param("att") == "units-turn@1"


def test_ops_for_media_type_pdf_reaches_promoted_image_ops(tmp_path):
    root = _corpus(tmp_path)
    ops = resolver.ops_for_media_type(root, "application/pdf")
    by_param_kind = {(op.param, op.from_kind) for op in ops}
    # Direct pdf ops.
    assert ("page", "pdf") in by_param_kind
    assert ("probe", "pdf") in by_param_kind
    assert ("outline", "pdf") in by_param_kind
    # Follow-on ops on the intermediate `pdfpage` selector.
    assert ("text", "pdfpage") in by_param_kind
    assert ("words", "pdfpage") in by_param_kind
    # Image-kind ops, reachable via the resolver's pdfpage->image auto-promotion.
    assert ("bbox", "image") in by_param_kind
    assert ("crop", "image") in by_param_kind


def test_ops_for_media_type_no_pipeline_is_empty(tmp_path):
    root = _corpus(tmp_path)
    assert resolver.ops_for_media_type(root, "application/json") == []


def test_working_kind_for_matches_ops_for_media_type_root(tmp_path):
    root = _corpus(tmp_path)
    assert resolver.working_kind_for(root, "text/csv") == "csv"
    assert resolver.working_kind_for(root, "application/json") is None


# ---------- CLI: no-pipeline mime honesty ---------- #


def test_inspect_no_pipeline_mime_honesty(tmp_path, capsys):
    root = _corpus(tmp_path)
    rid = _stage(root, b'{"a": 1}', mime="application/json", name="data.json")
    rc = dispatch(["inspect", rid, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert (
        "mime pipeline: none registered for media_type 'application/json' "
        "(no `working_kind:` declared on its mime schema, and no built-in fallback)"
    ) in out


# ---------- CLI: zip container — path= ops + member re-chaining note ---------- #


def test_inspect_zip_container_shows_path_op_and_rechain_note(tmp_path, capsys):
    root = _corpus(tmp_path)
    zpath = root.parent / "bundle.zip"
    with zipfile.ZipFile(zpath, "w") as zf:
        zf.writestr("a.txt", "hello")
        zf.writestr("b.json", "{}")
    data = zpath.read_bytes()
    rid = _stage(
        root, data, mime="application/zip", name="bundle.zip",
        embeds=[
            {"media_type": "text/plain", "address": "path=a.txt", "transport": "blake3:aaa"},
            {"media_type": "application/json", "address": "path=b.json", "transport": "blake3:bbb"},
        ],
    )
    rc = dispatch(["inspect", rid, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "embeds:      2 (container)" in out
    assert "mime pipeline (initial kind: zip):" in out
    assert "from zip: path= -> bytes" in out
    assert "Member re-chaining" in out
    assert "members -> json (2 embed(s))" in out


# ---------- CLI: prefix resolution ---------- #


def test_inspect_resolves_hex_prefix(tmp_path, capsys):
    root = _corpus(tmp_path)
    rid = _stage(root, b"city,fare\r\nCalgary,11\r\n", mime="text/csv", name="t.csv")
    rc = dispatch(["inspect", rid[:10], "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert f"record:      {rid}" in out


# ---------- CLI: every section prints honestly on a bare/empty record ---------- #


def test_inspect_empty_sections_honesty(tmp_path, capsys):
    root = _corpus(tmp_path)
    rid = _stage(
        root, b"city,fare\r\n", mime="text/csv", name="empty.csv", with_origin=False
    )
    rc = dispatch(["inspect", rid, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "title:       (none)  (layer: none)" in out
    assert "description: (none)  (layer: none)" in out
    assert "== origins (0) ==" in out
    assert "none" in out.splitlines()[out.splitlines().index("== origins (0) ==") + 1]
    assert "sections:    0 section(s), 0 segment(s)" in out
    assert "axes:        none" in out
    assert "embeds:      none" in out


def test_inspect_no_artifact_block_honesty(tmp_path, capsys):
    root = _corpus(tmp_path)
    # Stage a record with NO artifact block at all (mime=None skips set_artifact_block).
    rid = _stage(root, b"whatever", mime=None, name="raw.bin", with_origin=False)
    rc = dispatch(["inspect", rid, "--corpus-root", str(root)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "mime:        none — no <!--artifact--> block" in out
    assert "mime pipeline: n/a — no <!--artifact--> block" in out
    assert "record-level: none" in out


# ---------- CLI: malformed content zone degrades, never crashes ---------- #


def test_inspect_malformed_content_zone_degrades(tmp_path, capsys):
    root = _corpus(tmp_path)
    rid = _stage(
        root, b"a,b\r\n1,2\r\n", mime="text/csv", name="bad.csv",
        content="<!--segment text\naddress: turn=1\n-->\n\nunterminated body without a closer",
    )
    # Force a malformed content zone directly (an unterminated segment header) after
    # staging, since `_stage` would otherwise round-trip valid grammar.
    rf = paths.record_path(root, rid)
    text = rf.read_text(encoding="utf-8")
    text = text.replace(
        "<!--segment text\naddress: turn=1\n-->\n\nunterminated body without a closer",
        "<!--segment text\naddress: turn=1\nno closer here at all",
    )
    rf.write_text(text, encoding="utf-8")

    rc = dispatch(["inspect", rid, "--corpus-root", str(root)])
    assert rc == 0  # never crashes
    out = capsys.readouterr().out
    assert "(parse error:" in out
