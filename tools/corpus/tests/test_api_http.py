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


def test_records_and_detail(client):
    r = client.get("/v1/test/records")
    assert r.status_code == 200
    r = client.get(f"/v1/test/records/{_IMG_ID}")
    assert r.status_code == 200
    assert r.json()["title"] == "Wiring Diagram"


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
