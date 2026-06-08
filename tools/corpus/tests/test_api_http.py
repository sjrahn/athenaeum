"""HTTP integration tests for the corpus API (FastAPI TestClient).

Import-skipped unless the `[api]` extra (fastapi) AND httpx are installed, so the
no-extra suite and the base-import guard (`import corpus.draft` without `[api]`) stay
green (gotcha #24/#72). Run with: `uv run --extra api pytest tests/test_api_http.py`.

Covers the JSON read routes end-to-end plus the new `/regions` write surface. Binary
serving via `/resolve` (transform pipelines) is left to live verification; `/artifacts`
is smoked with a real on-disk PNG.
"""

from __future__ import annotations

import base64
from pathlib import Path

import frontmatter
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient

from corpus import records, schemas, segments
from corpus.api import config as api_config
from corpus.api.app import create_app
from corpus.api.config import ApiConfig

# A 1x1 transparent PNG.
_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk"
    "+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)
_IMG_ID = "a" * 64
_PDF_ID = "c" * 64


def _build_corpus(root: Path) -> None:
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    (root / "artifacts").mkdir()
    schemas._sources.cache_clear()

    # Image record + real artifact bytes (for /artifacts).
    img = frontmatter.Post("")
    img.metadata.update(
        {
            "id": _IMG_ID,
            "title": "Wiring Diagram",
            "description": "An image.",
            "status": "normalized",
            "transport": "blake3:" + "b" * 64,
            "touch": ["corpus.ingest@0.1.0", "corpus.draft.mime/image/png@0.1.0"],
        }
    )
    records.set_artifact_block(img, mime="image/png", fields={"title": "diagram"})
    records.append_origin_block(
        img, uri="https://example.com/d.png", snapshot="2026-06-01T00:00:00Z"
    )
    img.content = segments.emit([segments.Segment(atom="image", address="bbox=0,0,1,1", body="")])
    records.dump(img, root / "records" / "aa" / f"{_IMG_ID}.md")
    (root / "artifacts" / "aa").mkdir(parents=True)
    (root / "artifacts" / "aa" / f"{_IMG_ID}.png").write_bytes(_PNG)

    # PDF record (sectioned), no artifact bytes needed for these tests.
    pdf = frontmatter.Post("")
    pdf.metadata.update(
        {
            "id": _PDF_ID,
            "title": "Service Bulletin",
            "description": "A bulletin.",
            "status": "normalized",
            "transport": "sha256:" + "d" * 64,
            "touch": ["corpus.ingest@0.1.0", "corpus.draft.mime/application/pdf@0.1.0"],
        }
    )
    records.set_artifact_block(pdf, mime="application/pdf", fields={"title": "SB", "page_count": 2})
    pdf.content = segments.emit(
        [
            segments.Section(
                address="pages=1-2",
                entry="Body",
                segments=[
                    segments.Segment(atom="text", address="page=1", body="One."),
                    segments.Segment(atom="text", address="page=2", body="Two."),
                ],
            )
        ]
    )
    # A concept annotation (§4.3.3.4) — exercises the detail `concepts` view + the `concept` facet.
    records.append_context_block(
        pdf,
        namespace="concept",
        id="concept",
        fields={
            "address": "page=1",
            "quote": "service",
            "concept": "wikidata:Q42",
            "label": "Service Manual",
            "url": "https://en.wikipedia.org/wiki/Service_Manual",
        },
    )
    records.dump(pdf, root / "records" / "cc" / f"{_PDF_ID}.md")


@pytest.fixture
def client(tmp_path) -> TestClient:
    root = tmp_path / "corpus"
    _build_corpus(root)
    cfg = ApiConfig([api_config._entry("test", root, 0)])
    return TestClient(create_app(cfg))


# ---------- read routes ---------- #


def test_health(client):
    r = client.get("/v1/health")
    assert r.status_code == 200
    assert r.text == "ok"


def test_corpora(client):
    r = client.get("/v1/corpora")
    assert r.status_code == 200
    ids = [c["id"] for c in r.json()]
    assert ids == ["test"]
    assert r.json()[0]["record_count"] == 2


def test_workbench_shape(client):
    r = client.get("/v1/test/workbench")
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 2
    for key in ("records", "facetStack", "timeline", "availableFields", "overview"):
        assert key in body
    # every row carries the canonical artifact filename (B1) for the untitled placeholder
    assert all("transport_name" in rec for rec in body["records"])
    img = next(rec for rec in body["records"] if rec["id"] == _IMG_ID)
    assert img["transport_name"] == "aaaaaaaaaaaa.png"


def test_workbench_tokens(client):
    """Every row carries the three cumulative token tiers (the derived-view field)."""
    body = client.get("/v1/test/workbench").json()
    for rec in body["records"]:
        for k in ("tokens_body", "tokens_blocks", "tokens_full"):
            assert isinstance(rec[k], int), rec
        assert rec["tokens_body"] <= rec["tokens_blocks"] <= rec["tokens_full"]
    # the PDF record has real body text, so its body count is non-zero
    pdf = next(rec for rec in body["records"] if rec["id"] == _PDF_ID)
    assert pdf["tokens_body"] > 0


def test_fields_includes_tokens(client):
    """The token tiers are exposed as filterable numeric core fields with histogram stats."""
    fields = {f["id"]: f for f in client.get("/v1/test/fields").json()}
    for fid in ("core::tokens_body", "core::tokens_blocks", "core::tokens_full"):
        assert fid in fields, fields.keys()
        assert fields[fid]["type"] == "number"
        assert fields[fid]["group"] == "core"
    assert "bins" in fields["core::tokens_full"]["stats"]


def test_tokens_between_filter_narrows(client):
    """A numeric `between` condition on a token field narrows the set (the range brush)."""
    full = client.get("/v1/test/workbench").json()
    assert full["total"] == 2
    # body==0 matches only the image record (its single segment is a body-empty image marker)
    narrowed = client.get(
        "/v1/test/workbench", params={"cond": "core::tokens_body~number~between~0,0"}
    ).json()
    assert narrowed["total"] == 1
    assert narrowed["records"][0]["id"] == _IMG_ID


def test_records_and_detail(client):
    r = client.get("/v1/test/records")
    assert r.status_code == 200
    r = client.get(f"/v1/test/records/{_IMG_ID}")
    assert r.status_code == 200
    body = r.json()
    assert body["title"] == "Wiring Diagram"
    # the detail carries the token breakdown for the inspector/detail pane
    assert set(body["tokens"]) == {"body", "blocks", "full"}
    assert body["tokens"]["body"] <= body["tokens"]["blocks"] <= body["tokens"]["full"]


def test_record_detail_includes_concepts(client):
    """The detail carries the `concepts` view; with no KB there's no live summary enrichment."""
    body = client.get(f"/v1/test/records/{_PDF_ID}").json()
    assert "concepts" in body
    cs = body["concepts"]
    assert len(cs) == 1
    assert cs[0]["concept"] == "wikidata:Q42"
    assert cs[0]["label"] == "Service Manual"
    assert cs[0]["address"] == "page=1"
    assert "summary" not in cs[0]


def test_concept_facet_and_filter(client):
    """A `concept` facet group surfaces (labelled by display name) and `facet=concept=…` filters."""
    body = client.get("/v1/test/workbench").json()
    groups = {g["key"]: g for g in body["facetStack"]}
    assert "concept" in groups
    vals = {v["v"]: v["label"] for v in groups["concept"]["values"]}
    assert vals == {"wikidata:Q42": "Service Manual"}

    narrowed = client.get("/v1/test/workbench", params={"facet": "concept=wikidata:Q42"}).json()
    assert narrowed["total"] == 1
    assert narrowed["records"][0]["id"] == _PDF_ID


def test_wiki_endpoints_503_without_kb(client):
    assert client.get("/v1/wiki/search", params={"q": "entropy"}).status_code == 503
    assert client.get("/v1/wiki/article", params={"id": "Entropy"}).status_code == 503


def _build_zim(path: Path) -> None:
    from libzim.writer import Creator, Hint, Item, StringProvider

    class _H(Item):
        def __init__(self, p, t, c):
            super().__init__()
            self._p, self._t, self._c = p, t, c

        def get_path(self):
            return self._p

        def get_title(self):
            return self._t

        def get_mimetype(self):
            return "text/html"

        def get_contentprovider(self):
            return StringProvider(self._c)

        def get_hints(self):
            return {Hint.FRONT_ARTICLE: True}

    body = (
        "<html><head><title>Service Manual</title>"
        '<link rel="canonical" href="https://www.wikidata.org/wiki/Q42"></head>'
        "<body><p>A service manual is a maintenance document for a product, "
        "long enough to be a real summary.</p></body></html>"
    )
    with Creator(str(path)).config_indexing(True, "eng") as creator:
        creator.add_item(_H("Service Manual", "Service Manual", body))
        creator.set_mainpath("Service Manual")


def test_wiki_kb_enriches_detail_and_endpoints(tmp_path):
    """With a ZIM configured: detail concepts gain a live gloss, and /v1/wiki/* serve."""
    pytest.importorskip("libzim")
    root = tmp_path / "corpus"
    _build_corpus(root)
    zim = tmp_path / "w.zim"
    _build_zim(zim)
    cfg = ApiConfig([api_config._entry("test", root, 0)], wiki_zim=str(zim))
    c = TestClient(create_app(cfg))

    # detail enrichment: the concept (label "Service Manual") gets a live summary + source.
    cs = c.get(f"/v1/test/records/{_PDF_ID}").json()["concepts"]
    assert cs[0]["summary"].startswith("A service manual is a maintenance document")
    assert cs[0]["source"] == "wikipedia"

    # /v1/wiki/search
    hits = c.get("/v1/wiki/search", params={"q": "maintenance"}).json()
    assert any(h["title"] == "Service Manual" for h in hits)

    # /v1/wiki/article
    art = c.get("/v1/wiki/article", params={"id": "Service Manual"}).json()
    assert art["qid"] == "wikidata:Q42"
    assert art["summary"].startswith("A service manual")


def test_schema_fields_facets(client):
    for path in ("/v1/test/schema", "/v1/test/fields", "/v1/test/facets"):
        assert client.get(path).status_code == 200


def test_artifact_bytes_get_and_head(client):
    r = client.get(f"/v1/test/artifacts/{_IMG_ID}")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("image/png")
    assert r.content == _PNG
    assert client.head(f"/v1/test/artifacts/{_IMG_ID}").status_code == 200


def test_not_found(client):
    assert client.get("/v1/nope/records").status_code == 404
    assert client.get(f"/v1/test/records/{'e' * 64}").status_code == 404


def test_graph_route(client):
    r = client.get(f"/v1/test/records/{_IMG_ID}/graph")
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {"resolved", "uncaptured"}
    # the image record's origin shows as a resolved node; its body carries no outbound URLs
    origins = [n for n in body["resolved"] if n["kind"] == "origin"]
    assert origins and origins[0]["label"] == "example.com"
    assert body["uncaptured"] == []
    assert client.get(f"/v1/test/records/{'e' * 64}/graph").status_code == 404


# ---------- write route: /regions ---------- #


def test_regions_happy_path(client, tmp_path):
    r = client.post(
        f"/v1/test/records/{_IMG_ID}/regions",
        json={"regions": [{"box": [0.1, 0.2, 0.3, 0.4], "atom": "image"}]},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["bbox_segment_count"] == 1
    assert body["addresses"] == ["bbox=0.1,0.2,0.3,0.4"]
    assert body["touch"][-1] == "corpus.regions@0.1.0"

    # Reload the record from disk: the new bbox segment is persisted; title preserved.
    root = client.app.state.config.by_id("test").root
    post = records.load(root / "records" / "aa" / f"{_IMG_ID}.md")
    addrs = [b.address for b in segments.iter_blocks(post.content or "")]
    assert "bbox=0.1,0.2,0.3,0.4" in addrs
    assert post.metadata["title"] == "Wiring Diagram"


def test_regions_bad_overlay_is_400(client):
    r = client.post(
        f"/v1/test/records/{_IMG_ID}/regions",
        json={"regions": [{"box": [0.1, 0.1, 0.2, 0.2], "atom": "text", "overlay": "caption"}]},
    )
    assert r.status_code == 400


def test_regions_out_of_range_box_is_400(client):
    r = client.post(
        f"/v1/test/records/{_IMG_ID}/regions",
        json={"regions": [{"box": [0.1, 0.1, 1.5, 0.2], "atom": "image"}]},
    )
    assert r.status_code == 400


def test_regions_malformed_box_is_422(client):
    r = client.post(
        f"/v1/test/records/{_IMG_ID}/regions",
        json={"regions": [{"box": [0.1, 0.1], "atom": "image"}]},
    )
    assert r.status_code == 422


def test_regions_page_without_section_is_400(client):
    r = client.post(
        f"/v1/test/records/{_PDF_ID}/regions",
        json={"regions": [{"page": 9, "box": [0.1, 0.1, 0.2, 0.2], "atom": "image"}]},
    )
    assert r.status_code == 400


def test_regions_unknown_record_is_404(client):
    r = client.post(
        f"/v1/test/records/{'e' * 64}/regions",
        json={"regions": [{"box": [0.1, 0.1, 0.2, 0.2], "atom": "image"}]},
    )
    assert r.status_code == 404


def test_regions_bad_hex_is_400(client):
    r = client.post(
        "/v1/test/records/not-hex/regions",
        json={"regions": [{"box": [0.1, 0.1, 0.2, 0.2], "atom": "image"}]},
    )
    assert r.status_code == 400
