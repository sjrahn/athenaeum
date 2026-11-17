"""Word 97-2003 `.doc` drafting: the piece table put back in order, fields shown as their
results, tables as tab/line text — one address-less segment, so a quote verifies
record-wide. The fixture is a hand-built OLE2 compound file (no writer exists in the
dependency set): a FIB naming `1Table`, and a two-piece table mixing a Windows-1252 run with
a UTF-16 one.
"""

from __future__ import annotations

import struct

import pytest

from corpus.draft import doc as doc_draft

_ENDOFCHAIN, _FATSECT, _FREE, _NOSTREAM = 0xFFFFFFFE, 0xFFFFFFFD, 0xFFFFFFFF, 0xFFFFFFFF


def _cfb(streams: list[tuple[str, bytes]]) -> bytes:
    """A version-3 compound file: one FAT sector, one directory sector, then each stream
    (padded past the 4096-byte mini-stream cutoff, so every stream lives in the FAT)."""
    padded = [(n, d + b"\0" * (-len(d) % 512)) for n, d in streams]
    fat = [_FATSECT, _ENDOFCHAIN]
    starts = []
    for _, d in padded:
        start, count = len(fat), len(d) // 512
        starts.append(start)
        fat += [start + i + 1 for i in range(count - 1)] + [_ENDOFCHAIN]
    assert len(fat) <= 128
    fat += [_FREE] * (128 - len(fat))

    def entry(name: str, etype: int, child: int, right: int, start: int, size: int) -> bytes:
        raw = name.encode("utf-16-le") + b"\0\0"
        return (raw.ljust(64, b"\0") + struct.pack("<HBB", len(raw), etype, 1)
                + struct.pack("<III", _NOSTREAM, right, child) + b"\0" * 36
                + struct.pack("<IQ", start, size))

    dirs = entry("Root Entry", 5, 1, _NOSTREAM, _ENDOFCHAIN, 0)
    for i, ((name, d), start) in enumerate(zip(streams, starts, strict=True), start=1):
        right = i + 1 if i < len(streams) else _NOSTREAM
        dirs += entry(name, 2, _NOSTREAM, right, start, len(d))
    dirs = dirs.ljust(512, b"\0")
    header = (bytes.fromhex("d0cf11e0a1b11ae1") + b"\0" * 16
              + struct.pack("<HHHHH", 0x3E, 3, 0xFFFE, 9, 6) + b"\0" * 6
              + struct.pack("<IIIIIIIII", 0, 1, 1, 0, 4096, _ENDOFCHAIN, 0, _ENDOFCHAIN, 0)
              + struct.pack("<109I", 0, *([_FREE] * 108)))
    return header + struct.pack("<128I", *fat) + dirs + b"".join(d for _, d in padded)


def _doc(piece1: str, piece2: str) -> bytes:
    """`piece1` stored compressed (cp1252) at 0x800, `piece2` as UTF-16LE at 0x1000."""
    wd = bytearray(5000)
    struct.pack_into("<H", wd, 0, 0xA5EC)
    struct.pack_into("<H", wd, 0x0A, 0x0200)  # fWhichTblStm → 1Table
    struct.pack_into("<i", wd, 0x4C, len(piece1) + len(piece2))
    a = piece1.encode("cp1252")
    b = piece2.encode("utf-16-le")
    wd[0x800:0x800 + len(a)] = a
    wd[0x1000:0x1000 + len(b)] = b
    cps = [0, len(piece1), len(piece1) + len(piece2)]
    plc = struct.pack("<3I", *cps)
    plc += struct.pack("<HIH", 0, (0x800 * 2) | 0x40000000, 0)
    plc += struct.pack("<HIH", 0, 0x1000, 0)
    clx = b"\x02" + struct.pack("<I", len(plc)) + plc
    struct.pack_into("<II", wd, 0x1A2, 0, len(clx))
    table = clx.ljust(4200, b"\0")
    return _cfb([("WordDocument", bytes(wd)), ("1Table", table)])


_TEXT1 = ("Monitoring Manual\r\r\x0cTABLE OF CONTENTS\r"
          "\x13 HYPERLINK \\l \"_Toc1\" \x141.\tIntroduction\t"
          "\x13 PAGEREF _Toc1 \\h \x01\x143\x15\x15\r"
          "Meter\x07Reading\x07\x07M-1\x07 42\x07\x07")
_TEXT2 = "Flow µg/m³ — non\x1ebreaking\x0bnext line\r\x01\r"


def test_pieces_reassemble_and_render(tmp_path, run_drafter):
    src = tmp_path / "m.doc"
    src.write_bytes(_doc(_TEXT1, _TEXT2))
    result, blocks = run_drafter(doc_draft.draft, src)
    assert result["issues"] == []
    [seg] = blocks
    assert seg.address is None and seg.atom == "text"
    assert seg.body == (
        "Monitoring Manual\n\nTABLE OF CONTENTS\n\n1.\tIntroduction\t3\n\n"
        "Meter\tReading\nM-1\t 42\n"
        "Flow µg/m³ — non-breaking\nnext line\n"
    )


def test_not_a_word_document_drafts_no_body(tmp_path, run_drafter):
    src = tmp_path / "x.doc"
    src.write_bytes(b"\xd0\xcf\x11\xe0 not really")
    result, blocks = run_drafter(doc_draft.draft, src)
    assert blocks == []
    assert [(i["id"], i["subtype"]) for i in result["issues"]] == [
        ("partial-content", "empty-body")]


def test_an_encrypted_document_is_refused(tmp_path):
    data = bytearray(_doc("secret\r", ""))
    # the FIB sits at the start of the WordDocument stream: sector 2 of the file
    off = 512 * 3
    struct.pack_into("<H", data, off + 0x0A, 0x0200 | 0x0100)
    with pytest.raises(doc_draft.DocFormatError, match="encrypted"):
        doc_draft.read_main_text(bytes(data))


def test_a_drafted_doc_record_verifies_a_quote(tmp_path):
    import json

    from ledger.corpora import CorpusJoin, RegisteredCorpus
    from ledger.verify import verify_ledger
    from tests._draftlib import draft_for_test
    from tests.test_html_text_and_cid import _corpus, _stage_record

    root = _corpus(tmp_path)
    rid = _stage_record(root, _doc(_TEXT1, _TEXT2), mime="application/msword", name="m.doc")
    assert draft_for_test(root, rid) == 0
    ledger = root.parent / "ledger"
    (ledger / "facts" / "project").mkdir(parents=True)
    (ledger / "facts" / "project" / "p.json").write_text(json.dumps({
        "id": "p", "type": "project", "name": "P",
        "sources": {"s1": {"record": rid}},
        "claims": [{"id": "p:flow", "predicate": "flow-unit", "value": "µg/m³",
                    "status": "confirmed", "asof": "2026-11-17",
                    "evidence": [{"source": "s1", "quote": "Flow µg/m³ — non-breaking",
                                  "kind": "authoritative"}]}],
    }))
    join = CorpusJoin([RegisteredCorpus("corpus", root, private=False)])
    res = verify_ledger(ledger, join, {}, stamp=False, today="2026-11-17")
    assert not res.errors and res.verified == 1, (res.errors, res.notes)


def test_a_truncated_piece_table_is_a_format_error_not_a_crash(tmp_path, run_drafter):
    data = bytearray(_doc(_TEXT1, _TEXT2))
    off = 512 * 3  # the WordDocument stream's first sector
    struct.pack_into("<II", data, off + 0x1A2, 0, 9)  # lcbClx cuts the PlcPcd short
    with pytest.raises(doc_draft.DocFormatError):
        doc_draft.read_main_text(bytes(data))
    src = tmp_path / "t.doc"
    src.write_bytes(bytes(data))
    result, blocks = run_drafter(doc_draft.draft, src)
    assert blocks == [] and result["issues"][0]["id"] == "partial-content"
