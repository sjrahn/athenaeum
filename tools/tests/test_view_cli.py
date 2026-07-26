"""`corpus view` — the self-contained HTML projection: every addressed surface resolved
and inlined. Regression coverage for the double-inlined `<img>` (each surface's `data:`
URI was interpolated into both an `<a href>` wrapper and the `<img src>`)."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import frontmatter
from PIL import Image

from corpus import hashing, paths, records
from corpus._cli import dispatch
from corpus.store import LocalArtifactStore
from tests._draftlib import draft_for_test

_FIXTURES = Path(__file__).parent / "data"


def _stage(tmp_path: Path, fixture: str, *, mime: str, ext: str) -> tuple[Path, str]:
    """Ingest `fixture` as a stub record, then draft it in place so it carries the
    embed blocks and content segments a drafted record has — `corpus view` renders
    what's already on the record, it doesn't draft anything itself."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()

    src = _FIXTURES / fixture
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, ext, src)

    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "description": "",
            "transport": f"sha256:{h['sha256']}",
            "touch": "corpus.ingest@0.1.0",
        }
    )
    records.set_artifact_block(post, mime=mime, fields={})
    records.append_origin_block(
        post, uri=f"file://{src.resolve()}", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(root, rid))

    assert draft_for_test(root, rid) == 0
    return root, rid


def _png_data_uri(w: int, h: int, color: tuple[int, int, int]) -> str:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return "data:image/png;base64," + base64.b64encode(buf.getvalue()).decode()


def _stage_two_image_html(tmp_path: Path) -> tuple[Path, str]:
    """A minimal HTML artifact with two distinct inline PNGs — decodable data: URIs the
    drafter turns into two real image embeds, unlike an `<img src="https://...">` which
    wouldn't embed at all. Two DISTINCT images (not one repeated) so each gets its own
    embed block with a scalar `el=` address, keeping the surface count unambiguous."""
    html_str = (
        "<html><body><p>lede</p>"
        f'<figure><img src="{_png_data_uri(10, 8, (10, 20, 30))}" alt="Chart one"></figure>'
        "<p>middle</p>"
        f'<figure><img src="{_png_data_uri(20, 16, (200, 90, 10))}" alt="Chart two"></figure>'
        "</body></html>"
    )
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    src = tmp_path / "two-images.html"
    src.write_text(html_str, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)

    post = frontmatter.Post("")
    post.metadata.update(
        {
            "id": rid,
            "description": "",
            "transport": f"sha256:{h['sha256']}",
            "touch": "corpus.ingest@0.1.0",
        }
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(
        post, uri=f"file://{src.resolve()}", snapshot="2026-05-31T00:00:00Z"
    )
    records.dump(post, paths.record_path(root, rid))

    assert draft_for_test(root, rid) == 0
    return root, rid


def test_each_surface_is_inlined_once(tmp_path):
    """THE regression test: two distinct PNG embeds must each contribute exactly one
    `data:image` URI to the page, not two."""
    root, rid = _stage_two_image_html(tmp_path)
    out = tmp_path / "v.html"
    rc = dispatch(["view", rid, "-o", str(out), "--corpus-root", str(root)])
    assert rc == 0

    post = records.load(paths.record_path(root, rid))
    embeds = list(records.iter_embed_blocks(post))
    assert len(embeds) == 2  # sanity: the fixture actually yields the embeds it should

    page = out.read_text(encoding="utf-8")
    n_imgs = page.count("<img")
    n_data_uris = page.count("data:image")
    assert n_imgs == len(embeds)
    # One `data:` URI per rendered <img> — reintroducing the `<a href="{uri}">` wrapper
    # around the `<img src="{uri}">` doubles this count without changing n_imgs.
    assert n_data_uris == n_imgs


def test_image_surface_has_no_anchor_wrapper(tmp_path):
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    out = tmp_path / "v.html"
    rc = dispatch(["view", rid, "-o", str(out), "--corpus-root", str(root)])
    assert rc == 0
    page = out.read_text(encoding="utf-8")
    assert '<a href="data:' not in page
    assert "<img src=\"data:" in page  # the surface still renders, just unwrapped


def test_view_renders_segment_and_member_surfaces(tmp_path):
    """Smoke test: the page carries the record id, a members roster, and a content section."""
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    out = tmp_path / "v.html"
    rc = dispatch(["view", rid, "-o", str(out), "--corpus-root", str(root)])
    assert rc == 0
    page = out.read_text(encoding="utf-8")
    assert rid in page
    assert "members (3)" in page
    assert "segment (formless)" in page  # article.html drafts to one wrapping text segment


def test_placed_members_are_not_rendered_twice(tmp_path):
    """*(3.4)* The roster is an index, so it renders as metadata — a member the body already
    places is listed, never re-inlined. Before this, a page showed each asset twice: once raw
    at the top and once in the body at the derivation the record actually chose. On a record
    whose crops cover page chrome the raw copy is the LESS faithful of the two, and it was the
    first thing the eye landed on."""
    root, rid = _stage_two_image_html(tmp_path)
    out = tmp_path / "v.html"
    assert dispatch(["view", rid, "-o", str(out), "--corpus-root", str(root)]) == 0
    page = out.read_text(encoding="utf-8")

    post = records.load(paths.record_path(root, rid))
    members = list(records.iter_members(post))
    assert len(members) == 2
    assert f"members ({len(members)})" in page

    # Whatever the body places renders exactly once; the roster adds no further copies.
    placed = {str(m["address"]) for m in members}
    body_placed = sum(1 for a in placed if f'address: {a}' in (post.content or ""))
    assert page.count("data:image") == body_placed + page.count("UNPLACED")

    # And the roster row offers the recovery command instead of the bytes.
    assert "corpus resolve" in page


def test_page_budget_withholds_and_declares(tmp_path):
    """A truncated page that reads as exhaustive is the failure mode here, so the count of
    withheld surfaces is stated on the page rather than left to be inferred from its absence.
    The budget is charged in PAGE bytes (base64 is 4/3 of source), so the number the flag names
    is the number the output approaches."""
    root, rid = _stage_two_image_html(tmp_path)
    out = tmp_path / "v.html"
    # A budget of 1 byte withholds everything.
    assert dispatch(
        ["view", rid, "-o", str(out), "--max-inline", "1", "--corpus-root", str(root)]
    ) == 0
    page = out.read_text(encoding="utf-8")
    assert "data:image" not in page
    assert "withheld to keep the page openable" in page
    assert "surface(s) were not inlined" in page

    # 0 means unlimited — the escape hatch, and the A/B against the default.
    assert dispatch(
        ["view", rid, "-o", str(out), "--max-inline", "0", "--corpus-root", str(root)]
    ) == 0
    unlimited = out.read_text(encoding="utf-8")
    assert "data:image" in unlimited
    assert "surface(s) were not inlined" not in unlimited
