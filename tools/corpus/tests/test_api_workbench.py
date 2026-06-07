"""`corpus.api` workbench surface — server-side faceting.

Builds a tiny on-disk corpus (a normalized PDF, a draft HTML with a jpeg embed, a
normalized MP4) and drives `CorpusIndex.workbench()` directly — no FastAPI / `[api]`
extra needed (the index + serialize + the cond/range parsers are pure). Covers: the
combined response shape, drill-down narrowing (pure-AND), the embed-mime facet, facet
ordering + selected-but-absent injection, typed conditions (between/contains/in/date),
the timeline range scoping, the typed field registry, overview distributions, and the
`cond=`/`range=` query parsers.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter

from corpus import paths, records, segments
from corpus.api import index as wb_index
from corpus.api.config import CorpusEntry
from corpus.api.index import CorpusIndex, parse_cond, parse_range

PDF_ID = "a" * 64
HTML_ID = "b" * 64
MP4_ID = "c" * 64


def _corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    return root


def _record(
    root: Path,
    *,
    rid: str,
    mime: str,
    status: str,
    title: str,
    description: str,
    host: str,
    snapshot: str,
    artifact_fields: dict | None = None,
    genre: str | None = None,
    classify_fields: dict | None = None,
    embeds: list[dict] | None = None,
    blocks: list | None = None,
) -> None:
    post = frontmatter.Post(
        content="", **records.stub_frontmatter(record_id=rid, touch_id="corpus.ingest@0.1.0")
    )
    post.metadata["status"] = status
    post.metadata["title"] = title
    post.metadata["description"] = description
    records.set_artifact_block(post, mime=mime, fields=artifact_fields or {})
    records.append_origin_block(post, uri=f"https://{host}/x", snapshot=snapshot)
    if genre:
        records.append_classify_block(
            post, namespace="genre", id=genre, fields=classify_fields or {}
        )
    for e in embeds or []:
        records.append_embed_block(post, **e)
    if blocks:
        post.content = segments.emit(blocks)
    records.dump(post, paths.record_path(root, rid))


def _build(tmp_path: Path) -> CorpusIndex:
    root = _corpus(tmp_path)
    _record(
        root,
        rid=PDF_ID,
        mime="application/pdf",
        status="normalized",
        title="Trust Signals in Open Archives",
        description="An analysis of provenance.",
        host="arxiv.org",
        snapshot="2026-03-01T00:00:00Z",
        artifact_fields={"page_count": 12, "pdf_author": "Lindqvist", "pdf_created": "2026-01-15"},
        genre="paper",
        classify_fields={"topics": ["ml", "systems"]},
        blocks=[
            segments.Section(
                address="page=1-2",
                entry="Intro",
                segments=[
                    segments.Segment(atom="text", address="page=1", body="Hello world."),
                    segments.Segment(atom="text", address="page=2", body="More text."),
                ],
            )
        ],
    )
    _record(
        root,
        rid=HTML_ID,
        mime="text/html",
        status="draft",
        title="",
        description="",
        host="nytimes.com",
        snapshot="2026-03-15T00:00:00Z",
        genre="article",
        embeds=[
            {
                "media_type": "image/jpeg",
                "address": "el=2",
                "transport": "blake3:" + "d" * 64,
                "fields": {"width": 800, "height": 600, "alt": "figure"},
            }
        ],
        blocks=[
            segments.Segment(atom="text", address="el=1", body="A paragraph."),
            segments.Segment(atom="image", address="el=2"),
        ],
    )
    _record(
        root,
        rid=MP4_ID,
        mime="video/mp4",
        status="normalized",
        title="Compiler Talk",
        description="A conference talk.",
        host="youtube.com",
        snapshot="2026-04-01T00:00:00Z",
        artifact_fields={"duration": 600},
        genre="video",
        blocks=[segments.Segment(atom="video", address="time_range=0-10")],
    )
    entry = CorpusEntry(id="t", root=root, name="t", color="#a35a00", desc="")
    return CorpusIndex.build(entry)


# ---- shape + baseline ----


def test_workbench_shape_and_baseline(tmp_path):
    idx = _build(tmp_path)
    wb = idx.workbench()
    assert set(wb) == {"total", "records", "facetStack", "timeline", "availableFields", "overview"}
    assert wb["total"] == 3
    row = next(r for r in wb["records"] if r["id"] == PDF_ID)
    assert row["segments"] == 2  # two text segments
    assert "embed_count" in row and "captured" in row


def test_facet_stack_order_and_embedmime(tmp_path):
    idx = _build(tmp_path)
    wb = idx.workbench()
    keys = [f["key"] for f in wb["facetStack"]]
    # status · mime · embed-mime · origin · composite:* (no visibility — all unset)
    assert keys == ["status", "mime", "embedmime", "origin", "composite:genre"]
    embed = next(f for f in wb["facetStack"] if f["key"] == "embedmime")
    assert embed["values"] == [{"v": "jpg", "n": 1, "label": "jpg"}]
    mime = next(f for f in wb["facetStack"] if f["key"] == "mime")
    assert {v["v"] for v in mime["values"]} == {"application/pdf", "text/html", "video/mp4"}


def test_baseline_available_fields(tmp_path):
    idx = _build(tmp_path)
    avail = idx.workbench()["availableFields"]
    # title/description present on the normalized records; size_mb absent (no artifact bytes)
    assert "core::title" in avail
    assert "core::description" in avail
    assert "core::size_mb" not in avail
    # overlay fields are gated — not offered until their overlay is selected
    assert not any(a.startswith("mime/") for a in avail)


# ---- drill-down (pure-AND narrowing) ----


def test_drill_mime_collapses_and_gates_fields(tmp_path):
    idx = _build(tmp_path)
    wb = idx.workbench(facets={"mime": {"application/pdf"}})
    assert wb["total"] == 1
    mime = next(f for f in wb["facetStack"] if f["key"] == "mime")
    assert [v["v"] for v in mime["values"]] == ["application/pdf"]  # collapsed to the pick
    # the pdf overlay's extended fields are now available
    assert "mime/application/pdf::page_count" in wb["availableFields"]
    assert "mime/application/pdf::pdf_author" in wb["availableFields"]


def test_drill_embedmime(tmp_path):
    idx = _build(tmp_path)
    wb = idx.workbench(facets={"embedmime": {"jpg"}})
    assert wb["total"] == 1
    assert wb["records"][0]["id"] == HTML_ID


def test_selected_value_stays_visible_at_zero(tmp_path):
    idx = _build(tmp_path)
    # pdf is normalized, so pdf + draft is an empty set — but the picked mime stays shown
    wb = idx.workbench(facets={"mime": {"application/pdf"}, "status": {"draft"}})
    assert wb["total"] == 0
    mime = next(f for f in wb["facetStack"] if f["key"] == "mime")
    assert mime["values"] == [{"v": "application/pdf", "n": 0, "label": "pdf"}]


# ---- typed conditions ----


def _cond(fid: str, ctype: str, op: str, value) -> dict:
    return {"fid": fid, "type": ctype, "op": op, "value": value}


def test_cond_contains(tmp_path):
    idx = _build(tmp_path)
    cond = _cond("mime/application/pdf::pdf_author", "string", "contains", "lind")
    assert idx.workbench(conds=[cond])["total"] == 1


def test_cond_between_number(tmp_path):
    idx = _build(tmp_path)
    page = "mime/application/pdf::page_count"
    assert idx.workbench(conds=[_cond(page, "number", "between", [10, 20])])["total"] == 1
    assert idx.workbench(conds=[_cond(page, "number", "between", [0, 5])])["total"] == 0


def test_cond_in_list(tmp_path):
    idx = _build(tmp_path)
    topics = "composite/genre/paper::topics"
    assert idx.workbench(conds=[_cond(topics, "list", "in", ["ml"])])["total"] == 1
    assert idx.workbench(conds=[_cond(topics, "list", "in", ["rust"])])["total"] == 0


def test_cond_between_date(tmp_path):
    idx = _build(tmp_path)
    lo, hi = wb_index._date_to_ms("2026-01-01"), wb_index._date_to_ms("2026-02-01")
    cond = _cond("mime/application/pdf::pdf_created", "date", "between", [lo, hi])
    assert idx.workbench(conds=[cond])["total"] == 1


# ---- timeline ----


def test_timeline_bins_and_range_scope(tmp_path):
    idx = _build(tmp_path)
    wb = idx.workbench()
    tl = wb["timeline"]
    assert tl["binCount"] == 48 and len(tl["bins"]) == 48
    assert sum(b["n"] for b in tl["bins"]) == 3
    assert tl["inRange"]["count"] == 3  # no range -> everything
    # a March-only range keeps the arxiv + nytimes records, drops the April mp4
    mar = (wb_index._date_to_ms("2026-03-01"), wb_index._date_to_ms("2026-03-31"))
    wb_r = idx.workbench(rng=mar)
    assert wb_r["total"] == 2
    assert wb_r["timeline"]["inRange"]["count"] == 2


# ---- typed field registry ----


def test_fields_registry_types(tmp_path):
    idx = _build(tmp_path)
    by_id = {f["id"]: f for f in idx.fields()}
    assert by_id["mime/application/pdf::page_count"]["type"] == "number"
    assert by_id["mime/application/pdf::pdf_author"]["type"] == "string"
    assert by_id["mime/application/pdf::pdf_created"]["type"] == "date"
    assert by_id["composite/genre/paper::topics"]["type"] == "list"
    # number stats carry a histogram; string stats carry a value distribution
    assert "bins" in by_id["mime/application/pdf::page_count"]["stats"]
    assert "values" in by_id["mime/application/pdf::pdf_author"]["stats"]


# ---- overview ----


def test_overview_distributions(tmp_path):
    idx = _build(tmp_path)
    ov = idx.workbench()["overview"]
    assert ov["headline"]["records"] == 3
    assert ov["headline"]["pctNormalized"] == 67  # 2 of 3
    dists = ov["dists"]
    assert dict(dists["byStatus"]) == {"normalized": 2, "draft": 1}
    assert dict(dists["byGenre"]) == {"paper": 1, "article": 1, "video": 1}
    by_atom = dict(dists["byAtom"])
    assert by_atom["text"] == 3 and by_atom["image"] == 1 and by_atom["video"] == 1


# ---- query parsers ----


def test_parse_cond_variants():
    assert parse_cond("core::size_mb~number~between~0,5") == {
        "fid": "core::size_mb", "type": "number", "op": "between", "value": [0.0, 5.0],
    }
    assert parse_cond("f~date~between~100,200")["value"] == [100, 200]
    assert parse_cond("f~list~in~a,b,c")["value"] == ["a", "b", "c"]
    assert parse_cond("f~bool~is~true")["value"] is True
    assert parse_cond("f~string~contains~hello, world")["value"] == "hello, world"
    assert parse_cond("garbage") is None


def test_parse_range():
    assert parse_range("100,200") == (100, 200)
    assert parse_range("") is None
    assert parse_range("bad") is None
