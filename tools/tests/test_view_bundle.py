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
        [segments.Segment(atom="text", overlay="text/data-table", body="| a |\n|---|")]
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
