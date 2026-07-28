"""`corpus view` and the 3.8 placement bundle.

Every assertion here is a link that was dead. A placement's whole meaning is that the reading
lives on the member's own record, so a bundle that names the destination and cannot reach it
has projected the record wrongly — and a viewer's failures are silent by nature, which is why
they get tests rather than eyes.
"""

from __future__ import annotations

import base64
import zipfile
from pathlib import Path

import blake3
import frontmatter

from corpus import hashing, paths, records, schemas, segments
from corpus._cli import view as view_cli
from corpus.store import LocalArtifactStore

_PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAABfFcSJAAAADUlEQVR42mNk"
    "+M9QzwAEAAoAAv/lxKUAAAAASUVORK5CYII="
)
_PNG2 = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAABfFcSJAAAADUlEQVR42mP8z8BQzwAEYAYAJgIC/9r8"
    "0wAAAABJRU5ErkJggg=="
)
_PNG_HASH = blake3.blake3(_PNG).hexdigest()
_PNG2_HASH = blake3.blake3(_PNG2).hexdigest()
_MEMBER_HASHES = (_PNG_HASH, _PNG2_HASH)
_DATA_URI = "data:image/png;base64," + base64.b64encode(_PNG).decode()
_DATA_URI2 = "data:image/png;base64," + base64.b64encode(_PNG2).decode()


def _staged(tmp_path: Path, *, second_member: bool = False) -> tuple[Path, str]:
    """A parent that PLACES one member (or two), each with its own promoted record."""
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas.cache_clear()

    src = root / "page.html"
    second = f'<p><img src="{_DATA_URI2}"></p>' if second_member else ""
    src.write_text(
        f'<html><head><title>Page</title></head><body><div><p><img src="{_DATA_URI}"></p>'
        f"{second}</div></body></html>",
        encoding="utf-8",
    )
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)

    parent = frontmatter.Post("")
    parent.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    # The `addressing:` stamp is REQUIRED for an `el=` path member to materialize at all —
    # without it the resolver reads the address under the frozen legacy integer grammar and
    # refuses (§6.1.1), which is correct and is exactly what an unmigrated record hits.
    from bs4 import BeautifulSoup

    from corpus.transforms import html as html_tf

    elements = html_tf.total_element_count(
        BeautifulSoup(src.read_bytes(), html_tf.EL_PARSER_ID)
    )
    records.set_artifact_block(
        parent,
        mime="text/html",
        fields={"addressing": {"parser": html_tf.EL_PARSER_ID, "elements": elements}},
    )
    records.append_origin_block(parent, uri="https://x.test/p", snapshot="2026-01-01T00:00:00Z")
    records.append_member(
        parent,
        media_type="image/png",
        address="el=1.1.1",
        transport=f"blake3:{_PNG_HASH}",
        fields={"bytes": len(_PNG)},
    )
    placements = [segments.Segment(atom="placement", address="el=1.1.1")]
    if second_member:
        records.append_member(
            parent,
            media_type="image/png",
            address="el=1.2.1",
            transport=f"blake3:{_PNG2_HASH}",
            fields={"bytes": len(_PNG2)},
        )
        placements.append(segments.Segment(atom="placement", address="el=1.2.1"))
    parent.content = segments.emit(placements)
    records.dump(parent, paths.record_path(root, rid))

    leaf = frontmatter.Post("")
    leaf.metadata.update({"id": _PNG_HASH})
    records.set_artifact_block(leaf, mime="image/png", fields={})
    records.append_origin_block(
        leaf, uri=f"corpus://{rid}?el=1.1.1", snapshot="2026-01-01T00:00:00Z"
    )
    # The 3.8 shape: a rendering of the WHOLE transport, so no address at all.
    leaf.content = segments.emit(
        [segments.Segment(atom="text", overlay="text/data-table", body="| a |\n|---|\n| 1 |")]
    )
    records.dump(leaf, paths.record_path(root, _PNG_HASH))

    if second_member:
        leaf2 = frontmatter.Post("")
        leaf2.metadata.update({"id": _PNG2_HASH})
        records.set_artifact_block(leaf2, mime="image/png", fields={})
        records.append_origin_block(
            leaf2, uri=f"corpus://{rid}?el=1.2.1", snapshot="2026-01-01T00:00:00Z"
        )
        records.dump(leaf2, paths.record_path(root, _PNG2_HASH))
    return root, rid


class _Args:
    def __init__(self, **kw):
        self.__dict__.update(
            {
                "regenerate": False,
                "html": False,
                "max_inline": 0,
                "max_artifact": 0,
                "max_members": 25,
                "corpus_root": None,
                "out": None,
                **kw,
            }
        )


def _bundle(tmp_path: Path) -> zipfile.ZipFile:
    root, rid = _staged(tmp_path)
    out = tmp_path / "b.zip"
    assert view_cli.run(_Args(target=rid, out=str(out), corpus_root=str(root))) == 0
    return zipfile.ZipFile(out)


def test_a_placed_member_gets_a_folder_named_by_its_hash(tmp_path):
    """Same three names the bundle root carries — inside a container named by the id, plain
    names are what belong. It is also what makes the member page's own relative links true."""
    z = _bundle(tmp_path)
    names = set(z.namelist())
    folder = f"members/{_PNG_HASH}/"
    assert {folder + n for n in ("index.html", "record.md", "artifact.png")} <= names


def test_the_members_own_bytes_ride_with_it(tmp_path):
    """Materialized through containment — for a promoted member that means streamed out of
    the parent's own transport — so the folder is not a page talking about absent bytes."""
    z = _bundle(tmp_path)
    assert z.read(f"members/{_PNG_HASH}/artifact.png") == _PNG


def test_every_link_on_the_pages_resolves_inside_the_bundle(tmp_path):
    """The regression, stated as the property: no href in this bundle points at nothing.

    Both failures it replaces came from the flat layout — the member page emitted
    `href="record.md"` and `href="artifact.png"` relative to itself, which resolved to
    `members/record.md` and `members/artifact.png`."""
    import re

    z = _bundle(tmp_path)
    names = set(z.namelist())
    for page in (n for n in names if n.endswith("/index.html") or n == "index.html"):
        base = page.rsplit("/", 1)[0] + "/" if "/" in page else ""
        body = z.read(page).decode()
        hrefs = set(re.findall(r'<a class="?(?:tag member|file)"? href="([^"#]+)"', body))
        assert hrefs, f"{page} carries no file/member links at all"
        for href in hrefs:
            target = href if href.startswith("members/") else base + href
            assert target in names, f"{page}: dead link {href!r} → {target!r}"


def test_a_whole_transport_segment_resolves_its_surface(tmp_path):
    """*(3.8)* An absent address names the whole transport, and the bare `corpus://<id>` is
    how the resolver spells that. `_resolve_surface` used to return early on a falsy address —
    so the one surface a promoted member's page exists to show was the only one never asked
    for, and the page rendered a transcription with nothing beside it."""
    z = _bundle(tmp_path)
    leaf_page = z.read(f"members/{_PNG_HASH}/index.html").decode()
    assert "data:image/png;base64," in leaf_page


def test_an_absent_address_reads_as_the_whole_transport_not_as_none(tmp_path):
    """`None` in a reading view is a Python value leaking through, and it reads as a bug
    rather than as the statement the omission is."""
    z = _bundle(tmp_path)
    leaf_page = z.read(f"members/{_PNG_HASH}/index.html").decode()
    assert "the whole transport" in leaf_page
    assert ">None<" not in leaf_page


def test_the_parents_placement_links_to_the_members_page(tmp_path):
    z = _bundle(tmp_path)
    index = z.read("index.html").decode()
    assert f'href="members/{_PNG_HASH}/index.html"' in index
    # …and names what it found there, so the state is visible without following the link.
    assert _PNG_HASH[:12] in index


def test_the_cap_declines_to_link_rather_than_linking_nowhere(tmp_path):
    """Past `--max-members` the page names the member and prints the recovery line. A dead
    href would be worse than no href. (`--max-members 0` is UNLIMITED, matching the other two
    ceilings — so the cap is exercised with a real bound, not with zero.)"""
    root, rid = _staged(tmp_path, second_member=True)
    out = tmp_path / "capped.zip"
    assert view_cli.run(_Args(target=rid, out=str(out), corpus_root=str(root), max_members=1)) == 0
    z = zipfile.ZipFile(out)
    bundled = {n.split("/")[1] for n in z.namelist() if n.startswith("members/")}
    assert len(bundled) == 1
    index = z.read("index.html").decode()
    withheld = (set(_MEMBER_HASHES) - bundled).pop()
    assert f'href="members/{withheld}/index.html"' not in index
    assert f"corpus view {withheld}" in index


# ---------- segment bodies are RENDERED, and captured HTML is not trusted ---------- #


def test_an_html_table_body_renders_as_a_table(tmp_path):
    """A `text/data-table` whose transcription is a literal `<table>` — the drafter's shape for
    a table read out of HTML — used to land in a `<pre>`, which made the reader parse a table by
    eye. That is the one job this page exists to do for them."""
    out = view_cli._body_html(
        "<table><thead><tr><th rowspan=\"2\">A</th></tr></thead>"
        "<tbody><tr><td>1</td></tr></tbody></table>"
    )
    assert "<table>" in out and "<td>1</td>" in out
    assert 'rowspan="2"' in out  # load-bearing: merged headers are part of what it says
    assert "&lt;table&gt;" not in out


def test_a_captured_body_cannot_inject_script_or_handlers(tmp_path):
    """A record body is CAPTURED CONTENT, so the viewer assumes it contains anything the open
    web does. Whitelist, not blacklist: `lint` objects to script in a body, but a viewer that
    relied on the corpus being clean would be trusting a gate to hold for a page it hands to a
    person."""
    out = view_cli._body_html(
        '<table><tr><td onclick="steal()">x</td>'
        '<td><script>alert(1)</script></td>'
        '<td><a href="javascript:bad()">link</a></td></tr></table>'
    )
    assert "onclick" not in out
    assert "<script" not in out and "alert(1)" not in out  # dropped WITH its text
    assert "javascript:" not in out
    assert ">link<" in out  # the anchor's text survives; only the href goes


def test_markdown_bodies_render_rather_than_showing_their_source(tmp_path):
    out = view_cli._body_html(
        "## Fuse Block\n\n"
        "Some **bold** and `code` and [a link](https://x.test/p).\n\n"
        "- one\n- two\n\n"
        "| No. | Device |\n|---|---|\n| **FU1** | Not Used |\n"
    )
    assert "<h4>Fuse Block</h4>" in out  # demoted so it never outranks the page's own headings
    assert "<strong>bold</strong>" in out and "<code>code</code>" in out
    assert '<a href="https://x.test/p">a link</a>' in out
    assert "<li>one</li>" in out
    # …and a markdown cell is emphasis, not literal asterisks.
    assert "<td><strong>FU1</strong></td>" in out


def test_a_placement_imports_the_members_own_rendering(tmp_path):
    """§4.3.2.4 says the rendering is imported. Showing only the resolved pixels showed the one
    thing the parent still has and withheld the one thing the member added."""
    z = _bundle(tmp_path)
    index = z.read("index.html").decode()
    assert "class=imported" in index
    assert "imported from" in index
    assert "<th>a</th>" in index and "<td>1</td>" in index  # the leaf's table, on the parent


def test_a_body_empty_marker_on_the_leaf_imports_as_its_resolved_region(tmp_path):
    """A body-empty marker IS a rendering — §4.3.2.2's positioning marker is how a leaf says
    *this region is a figure*, and it is the only shape available when the content is pixels.

    The import first required a non-empty body, so a leaf that had divided its artifact into
    regions imported as nothing at all and the parent fell back to showing the member
    undivided — precisely the division the leaf exists to record, dropped on the floor. The
    marker's addresses are relative to the LEAF's bytes (§4.3.1.4, which is what makes them
    re-homeable), so they resolve against the member's own id, not the parent's.
    """
    root, rid = _staged(tmp_path)
    leaf_path = paths.record_path(root, _PNG_HASH)
    leaf = records.load(leaf_path)
    leaf.content = segments.emit(
        [
            segments.Segment(atom="structural", address="bbox=0,0,1,0.2", level=1, mark="Top"),
            segments.Segment(atom="image", address="bbox=0,0,0.5,1"),
            segments.Segment(atom="image", address="bbox=0.5,0,0.5,1"),
        ]
    )
    records.dump(leaf, leaf_path)

    out = tmp_path / "b.zip"
    assert view_cli.run(_Args(target=rid, corpus_root=str(root), out=str(out))) == 0
    index = zipfile.ZipFile(out).read("index.html").decode()

    assert "carries no rendering yet" not in index, "a marker-only leaf is not an empty leaf"
    assert "class=imported" in index
    # the leaf's own mark rides along, so the import reads the way the leaf reads
    assert ">Top <span class=tag>bbox=0,0,1,0.2</span></h4>" in index
    # …and each marker is carried on its own, at its own region
    imported = index.split("class=imported", 1)[1]
    for region in ("bbox=0,0,0.5,1", "bbox=0.5,0,0.5,1"):
        assert f">image <span class=tag>{region}</span></h4>" in imported

    # The assertion is structural rather than pixel-counting on purpose: `_PNG` is a 71-byte
    # stub that PIL cannot decode, so no crop resolves under this fixture. What regressed was
    # that markers never reached the import AT ALL — they were filtered out before any resolve
    # was attempted — and that is exactly what these three headings pin.
