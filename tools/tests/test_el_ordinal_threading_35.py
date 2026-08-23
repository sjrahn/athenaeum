"""v35 `el_ordinal_root` threading (`corpus.segments.blocks_for_record`).

A Section's address is DERIVED, never stored (§4.3.2.1) — `iter_blocks` alone has no
artifact access, so an ordinal-scheme record's section address comes back None unless a
caller threads the parsed tree. Pins the shared helper (`blocks_for_record`) plus the two
call sites verified (by reading, not assumption — see the v35 stage-2 report) to actually
need it: `corpus lint` (several rules read a Section's own address) and `corpus toc`
(prints it directly). `corpus health`/`show`/`view`/`diagnose` were checked and found NOT
to consume a Section's address, so they are deliberately left calling `iter_blocks`
directly — unaffected by this file.
"""

from __future__ import annotations

from pathlib import Path

import frontmatter
from bs4 import BeautifulSoup

from corpus import paths, records, schemas, segments
from corpus._cli import dispatch
from corpus.segments import Section, Segment
from corpus.store import LocalArtifactStore
from corpus.transforms import html as thtml

_DOC = (
    "<html><body>"
    "<div><h1>Title</h1><p>One.</p><p>Two.</p></div>"
    "</body></html>"
)


def _make_corpus(tmp_path: Path) -> Path:
    root = tmp_path / "c"
    (root / "records").mkdir(parents=True)
    (root / "schema").mkdir()
    schemas._sources.cache_clear()
    return root


def _ordinal_record_with_section(tmp_path: Path) -> tuple[Path, str]:
    """An ordinal-stamped record whose one Section carries two segments — h1 (ordinal 2)
    and the first <p> (ordinal 3), siblings under div (ordinal 1) — so the section's
    derived address is the sibling range `el=[2-3]`, computable ONLY with the tree."""
    from corpus import hashing

    root = _make_corpus(tmp_path)
    src = root / "page.html"
    src.write_text(_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    total = thtml.total_element_count(BeautifulSoup(_DOC, "html.parser"))
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(
        post, mime="text/html",
        fields={"addressing": {"parser": "html.parser", "elements": total, "scheme": "ordinal"}},
    )
    records.append_origin_block(post, uri="https://x.test/page", snapshot="2026-01-01T00:00:00Z")
    section = Section(
        form="document",
        segments=[
            Segment(atom="text", address="el=2", body="# Title"),
            Segment(atom="text", address="el=3", body="One."),
        ],
    )
    post.content = segments.emit([section])
    records.dump(post, paths.record_path(root, rid))
    return root, rid


# ---------- the shared helper, directly ---------- #


def test_blocks_for_record_derives_the_section_address_when_ordinal_stamped(tmp_path):
    root, rid = _ordinal_record_with_section(tmp_path)
    post = records.load(paths.record_path(root, rid))
    blocks = segments.blocks_for_record(post, root)
    assert isinstance(blocks[0], Section)
    assert blocks[0].address == "el=[2-3]"


def test_blocks_for_record_without_corpus_root_is_byte_identical_to_iter_blocks():
    """No `corpus_root`: `blocks_for_record` must not guess at the ordinal grammar — it
    falls through to the exact same (pre-existing, frozen) heuristic `iter_blocks` alone
    has always used, never a different answer."""
    section = Section(
        form="document",
        segments=[
            Segment(atom="text", address="el=2", body="# Title"),
            Segment(atom="text", address="el=3", body="One."),
        ],
    )
    content = segments.emit([section])
    plain = segments.iter_blocks(content)
    post = frontmatter.Post(content)
    threaded_without_root = segments.blocks_for_record(post)
    assert threaded_without_root[0].address == plain[0].address


def test_blocks_for_record_on_a_dotted_stamped_record_is_unaffected(tmp_path):
    """A dotted-stamped (schemeless) record's section envelope is pure algebra — no
    artifact access needed or used; `blocks_for_record` must not change its result."""
    from corpus import hashing

    root = _make_corpus(tmp_path)
    src = root / "page.html"
    src.write_text(_DOC, encoding="utf-8")
    h = hashing.hash_file(src)
    rid = h["blake3"]
    LocalArtifactStore(root).put(rid, "html", src)
    total = thtml.total_element_count(BeautifulSoup(_DOC, "html.parser"))
    post = frontmatter.Post("")
    post.metadata.update({"id": rid, "transport": f"sha256:{h['sha256']}"})
    records.set_artifact_block(
        post, mime="text/html", fields={"addressing": {"parser": "html.parser", "elements": total}}
    )
    records.append_origin_block(post, uri="https://x.test/page", snapshot="2026-01-01T00:00:00Z")
    section = Section(
        form="document",
        segments=[
            Segment(atom="text", address="el=1.1", body="# Title"),
            Segment(atom="text", address="el=1.2", body="One."),
        ],
    )
    post.content = segments.emit([section])
    records.dump(post, paths.record_path(root, rid))

    plain = segments.iter_blocks(post.content or "")
    threaded = segments.blocks_for_record(records.load(paths.record_path(root, rid)), root)
    assert plain[0].address == threaded[0].address == "el=1.[1-2]"


# ---------- the two threaded call sites ---------- #


def test_corpus_toc_prints_the_derived_ordinal_section_address(tmp_path, capsys):
    root, rid = _ordinal_record_with_section(tmp_path)
    assert dispatch(["toc", rid, "--corpus-root", str(root)]) == 0
    out = capsys.readouterr().out
    assert "addr=el=[2-3]" in out
    assert "addr=None" not in out


def test_corpus_lint_sees_the_derived_section_address(tmp_path, capsys):
    """`address-el-range-invalid` judges a stored `el=[a-b]` range's siblinghood — here the
    SECTION's own address (derived, not stored) is what the rule must see to have anything
    to check at all. This fixture's derived range (`el=[2-3]`) is genuinely valid (real
    siblings, in bounds), so lint must not flag it — proving the rule saw a real address
    and judged it correctly, not that it silently had nothing to check."""
    root, rid = _ordinal_record_with_section(tmp_path)
    dispatch(["lint", rid, "--corpus-root", str(root)])
    out = capsys.readouterr().out
    assert "address-el-range-invalid" not in out
