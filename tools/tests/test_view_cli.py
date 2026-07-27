"""`corpus view` — the self-contained HTML projection: every addressed surface resolved
and inlined. Regression coverage for the double-inlined `<img>` (each surface's `data:`
URI was interpolated into both an `<a href>` wrapper and the `<img src>`)."""

from __future__ import annotations

import base64
import io
import re
import zipfile
from pathlib import Path

import frontmatter
from PIL import Image

from corpus import hashing, paths, records
from corpus._cli import dispatch
from corpus._cli import view as view_mod
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


# ---------- the bundle (3.4-era `corpus view` default) ---------- #


def _bundle(tmp_path: Path, root: Path, rid: str, *extra: str) -> tuple[Path, zipfile.ZipFile]:
    out = tmp_path / "b.zip"
    assert dispatch(["view", rid, "-o", str(out), "--corpus-root", str(root), *extra]) == 0
    return out, zipfile.ZipFile(out)


def _page_of(zf: zipfile.ZipFile) -> str:
    return zf.read("index.html").decode("utf-8")


def _stage_repeated_image_html(tmp_path: Path) -> tuple[Path, str]:
    """One image used TWICE — which is how a list address arises: the roster dedups by
    `transport`, so both positions land on a single row whose `address` is a list."""
    uri = _png_data_uri(12, 9, (40, 60, 80))
    html_str = (
        f'<html><body><p>a</p><figure><img src="{uri}" alt="same"></figure>'
        f'<p>b</p><figure><img src="{uri}" alt="same"></figure></body></html>'
    )
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    src = tmp_path / "repeated.html"
    src.write_text(html_str, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    post = frontmatter.Post("")
    post.metadata.update(
        {"id": rid, "description": "", "transport": f"sha256:{h['sha256']}",
         "touch": "corpus.ingest@0.1.0"}
    )
    records.set_artifact_block(post, mime="text/html", fields={})
    records.append_origin_block(post, uri=f"file://{src.resolve()}",
                                snapshot="2026-05-31T00:00:00Z")
    records.dump(post, paths.record_path(root, rid))
    assert draft_for_test(root, rid) == 0
    return root, rid


def test_bundle_is_the_default_and_carries_three_members(tmp_path):
    """`corpus view` writes `<record-id>.zip` — artifact + record + page. The artifact is
    named for what it IS, not for its hash: inside a container already named by the id, the
    id adds nothing."""
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    assert dispatch(["view", rid, "--corpus-root", str(root)]) == 0
    out = root / "export" / f"{rid}.zip"
    assert out.is_file(), "the default output is the bundle, named for the record id"
    with zipfile.ZipFile(out) as zf:
        assert zf.testzip() is None
        assert sorted(zf.namelist()) == ["artifact.html", "index.html", "record.md"]
        # record.md is the record file VERBATIM — the point of shipping it.
        assert zf.read("record.md") == paths.record_path(root, rid).read_bytes()


def test_bundled_artifact_is_byte_identical(tmp_path):
    """The artifact rides verbatim. It is streamed rather than read whole (the ceiling admits
    256 MB by default), so a chunking bug would corrupt it silently — hence a byte compare
    rather than a size check."""
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    _, zf = _bundle(tmp_path, root, rid)
    source = LocalArtifactStore(root).local_path(rid, "html")
    with zf.open("artifact.html") as fh:
        assert fh.read() == source.read_bytes()


def test_bundle_rebuild_is_byte_identical(tmp_path):
    """Member mtimes and order are pinned, so the same record yields the same bundle. A viewer
    whose output wobbles with the filesystem invites "why did my bundle change" for no gain."""
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    first, _ = _bundle(tmp_path, root, rid)
    digest = hashing.hash_file(first)["blake3"]
    second, _ = _bundle(tmp_path, root, rid)
    assert hashing.hash_file(second)["blake3"] == digest


def test_page_declares_doctype_and_charset(tmp_path):
    """The page is opened from a `file://` path after someone unzips it, where a browser with
    no declared encoding falls back to a locale default and renders record titles (em-dashes,
    °, µ) as mojibake."""
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    _, zf = _bundle(tmp_path, root, rid)
    page = _page_of(zf)
    assert page.startswith("<!doctype html>")
    assert '<meta charset="utf-8">' in page


def test_page_carries_both_views_and_sibling_links(tmp_path):
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    _, zf = _bundle(tmp_path, root, rid)
    page = _page_of(zf)
    assert "id=view-read" in page and "id=view-src" in page
    assert 'href="record.md"' in page and 'href="artifact.html"' in page
    # The source view is the record verbatim, so its own block openers must be ESCAPED —
    # emitting them live would make the record's markup part of the page.
    assert "&lt;!--artifact" in page
    assert "<!--artifact" not in page.split("id=view-src", 1)[1]


def test_every_source_address_link_has_a_target(tmp_path):
    """THE invariant of the cross-link: an address in the record source must land on the block
    that materialized it. A dangling `#at-…` is worse than no link — it reads as navigable and
    silently does nothing."""
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    _, zf = _bundle(tmp_path, root, rid)
    page = _page_of(zf)
    ids = set(re.findall(r'\sid="([^"]+)"', page))
    targets = set(re.findall(r'href="#([^"]+)"', page))
    assert targets, "the source view linked no addresses at all"
    assert not targets - ids, f"dangling anchors: {sorted(targets - ids)}"
    duplicated = [i for i in ids if page.count(f'id="{i}"') > 1]
    assert not duplicated, f"duplicate DOM ids: {duplicated}"


def test_list_address_gets_a_target_per_position(tmp_path):
    """A list address is one asset at several positions and the source view links every one of
    them, but an element carries a single id — so the extras become alias targets. Without them
    the second position's link dangles."""
    root, rid = _stage_repeated_image_html(tmp_path)
    post = records.load(paths.record_path(root, rid))
    members = list(records.iter_members(post))
    assert len(members) == 1, "the fixture should dedup to ONE row"
    addrs = members[0]["address"]
    assert isinstance(addrs, list) and len(addrs) == 2, f"expected a list address, got {addrs!r}"

    _, zf = _bundle(tmp_path, root, rid)
    page = _page_of(zf)
    ids = set(re.findall(r'\sid="([^"]+)"', page))
    for addr in addrs:
        assert view_mod._anchor(addr) in ids, f"no jump target for {addr}"
    assert not set(re.findall(r'href="#([^"]+)"', page)) - ids


def test_artifact_ceiling_omits_and_declares(tmp_path):
    """The one member with no natural bound. Past the ceiling the bundle is still written and
    still useful — the omission is stated on the page and on stderr, never silent."""
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    _, zf = _bundle(tmp_path, root, rid, "--max-artifact", "1")
    assert sorted(zf.namelist()) == ["index.html", "record.md"]
    page = _page_of(zf)
    assert "NOT bundled" in page
    assert "--max-artifact" in page  # the page says how to get it

    # 0 = unlimited, the escape hatch and the A/B against the ceiling.
    out2 = tmp_path / "unlimited.zip"
    assert dispatch(
        ["view", rid, "-o", str(out2), "--max-artifact", "0", "--corpus-root", str(root)]
    ) == 0
    with zipfile.ZipFile(out2) as zf2:
        assert "artifact.html" in zf2.namelist()


def test_missing_artifact_still_yields_a_bundle(tmp_path):
    """Artifact bytes are not guaranteed resident (the open durable-storage question), and a
    record whose bytes are gone is exactly when you most want to look at it. The bundle is
    written one member short, and says so."""
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    LocalArtifactStore(root).local_path(rid, "html").unlink()
    _, zf = _bundle(tmp_path, root, rid)
    assert sorted(zf.namelist()) == ["index.html", "record.md"]
    assert "NOT bundled" in _page_of(zf)


def test_html_suffix_and_flag_both_yield_a_page(tmp_path):
    """`-o page.html` writing a zip named `page.html` is a lie the filesystem repeats to every
    tool downstream, so the suffix decides; `--html` forces it regardless of name."""
    root, rid = _stage(tmp_path, "article.html", mime="text/html", ext="html")
    by_suffix = tmp_path / "page.html"
    assert dispatch(["view", rid, "-o", str(by_suffix), "--corpus-root", str(root)]) == 0
    assert by_suffix.read_text(encoding="utf-8").startswith("<!doctype html>")

    by_flag = tmp_path / "named-anything"
    assert dispatch(
        ["view", rid, "--html", "-o", str(by_flag), "--corpus-root", str(root)]
    ) == 0
    assert by_flag.read_text(encoding="utf-8").startswith("<!doctype html>")
    # A page alone carries no sibling files, so it must not advertise them.
    assert 'href="record.md"' not in by_flag.read_text(encoding="utf-8")
