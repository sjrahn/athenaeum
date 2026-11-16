"""docx exposable members at `block=<N>&el=<K>`, and the `block=` resolver (spec §7.1, v47.1).

A docx's pictures and OLE objects are rostered as members addressed by the block that
draws them and their position inside it (EPUB's `spine=N&el=K` shape), and `block=N`
resolves to the block's text exactly as the drafter renders it.
"""

from __future__ import annotations

import io
import zipfile
from pathlib import Path

import pytest
from PIL import Image

from corpus import paths, records, resolver
from corpus.draft import docx as docx_draft
from tests.test_office import _DOCX_MIME, _setup

_NS = (
    'xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
    'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
    'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
    'xmlns:v="urn:schemas-microsoft-com:vml" '
    'xmlns:o="urn:schemas-microsoft-com:office:office" '
    'xmlns:mc="http://schemas.openxmlformats.org/markup-compatibility/2006"'
)


def _blip(rid: str) -> str:
    return f'<w:r><w:drawing><a:graphic><a:blip r:embed="{rid}"/></a:graphic></w:drawing></w:r>'


def _vml(rid: str) -> str:
    return f'<w:r><w:pict><v:shape><v:imagedata r:id="{rid}"/></v:shape></w:pict></w:r>'


_DOC = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document {_NS}><w:body>
  <w:p><w:r><w:t>Opening text.</w:t></w:r></w:p>
  <w:p>{_blip("rIdA")}</w:p>
  <w:p><w:r><w:t>Figure 1. A caption.</w:t></w:r></w:p>
  <w:p><mc:AlternateContent>
    <mc:Choice Requires="wps">{_blip("rIdB")}</mc:Choice>
    <mc:Fallback>{_vml("rIdB")}</mc:Fallback>
  </mc:AlternateContent>{_blip("rIdLink")}{_vml("rIdC")}</w:p>
  <w:p><w:r><w:object><v:shape><v:imagedata r:id="rIdC"/></v:shape>
    <o:OLEObject Type="Embed" ProgID="Excel.Sheet.12" r:id="rIdOle"/></w:object></w:r></w:p>
  <w:tbl><w:tr><w:tc><w:p><w:r><w:t>cell</w:t></w:r></w:p></w:tc>
    <w:tc><w:p>{_blip("rIdA")}</w:p></w:tc></w:tr></w:tbl>
</w:body></w:document>
"""

_RELS = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rIdA" Type="image" Target="media/image1.png"/>
  <Relationship Id="rIdB" Type="image" Target="media/image2.png"/>
  <Relationship Id="rIdC" Type="image" Target="media/image3.png"/>
  <Relationship Id="rIdOle" Type="oleObject" Target="embeddings/sheet1.xlsx"/>
  <Relationship Id="rIdLink" Type="image" Target="https://example.com/x.png" TargetMode="External"/>
</Relationships>
"""


def _png(color: tuple[int, int, int], size: tuple[int, int]) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()


_IMG1, _IMG2, _IMG3 = _png((200, 0, 0), (8, 4)), _png((0, 200, 0), (6, 6)), _png((0, 0, 9), (3, 5))
_OLE = b"PK\x03\x04 not really a workbook"


def _make(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("word/document.xml", _DOC)
        zf.writestr("word/_rels/document.xml.rels", _RELS)
        zf.writestr("word/media/image1.png", _IMG1)
        zf.writestr("word/media/image2.png", _IMG2)
        zf.writestr("word/media/image3.png", _IMG3)
        zf.writestr("word/embeddings/sheet1.xlsx", _OLE)


@pytest.fixture
def docx_record(tmp_path):
    src = tmp_path / "doc.docx"
    _make(src)
    rid = "d1" * 32
    return _setup(tmp_path, rid, "docx", _DOCX_MIME, src), rid, src


def test_drafter_rosters_every_drawn_part_by_block_and_position(docx_record, run_drafter):
    _root, _rid, src = docx_record
    result, _blocks = run_drafter(docx_draft.draft, src)
    # mc:Fallback's repeat of rIdB is not counted, and the external link is no member: block 4
    # holds exactly the Choice picture (el=1) and the VML picture (el=2)
    by_addr = {a: r for r in result["embeds"]
               for a in ([r["address"]] if isinstance(r["address"], str) else r["address"])}
    assert set(by_addr) == {"block=2&el=1", "block=6&el=1", "block=4&el=1", "block=4&el=2",
                            "block=5&el=1", "block=5&el=2"}
    assert by_addr["block=2&el=1"]["media_type"] == "image/png"
    assert by_addr["block=2&el=1"]["fields"] == {"bytes": len(_IMG1), "width": 8, "height": 4}
    assert by_addr["block=4&el=2"] is by_addr["block=5&el=1"]  # image3, drawn twice
    assert by_addr["block=5&el=2"]["fields"]["bytes"] == len(_OLE)


def test_block_resolves_to_the_drafters_text(docx_record):
    root, rid, _src = docx_record
    out = resolver.resolve(f"corpus://{rid}?block=3", root)
    assert out.read_text("utf-8") == "Figure 1. A caption.\n"
    out = resolver.resolve(f"corpus://{rid}?block=1-3", root)
    assert out.read_text("utf-8") == "Opening text.\n\nFigure 1. A caption.\n"
    assert resolver.can_yield_text(root, _DOCX_MIME, [("block", "3")])


def test_block_el_serves_the_member_bytes_verbatim(docx_record):
    root, rid, _src = docx_record
    out = resolver.resolve(f"corpus://{rid}?block=2&el=1", root)
    assert out.read_bytes() == _IMG1 and out.suffix == ".png"
    assert resolver.resolve(f"corpus://{rid}?block=4&el=2", root).read_bytes() == _IMG3
    assert resolver.resolve(f"corpus://{rid}?block=5&el=2", root).read_bytes() == _OLE
    with pytest.raises(Exception, match="out of range"):
        resolver.resolve(f"corpus://{rid}?block=3&el=1", root)


def test_reattested_record_carries_the_member_rows(docx_record):
    from tests._draftlib import draft_for_test

    root, rid, _src = docx_record
    assert draft_for_test(root, rid) == 0
    post = records.load(paths.record_path(root, rid))
    addrs = {a for row in records.iter_members(post)
             for a in ([row["address"]] if isinstance(row["address"], str) else row["address"])}
    assert "block=2&el=1" in addrs and "block=5&el=2" in addrs
