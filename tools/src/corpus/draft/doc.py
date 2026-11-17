"""Word 97-2003 binary documents (`application/msword`, `.doc`) — the main document text.

A `.doc` is an OLE2 Compound Document: its characters live in the `WordDocument` stream,
scattered across PIECES the piece table (the FIB's `Clx`, in the `0Table`/`1Table`
stream) puts back in order — 8-bit Windows-1252 runs and UTF-16LE runs alike. The drafter
reads the first `ccpText` characters (the main document story; headers, footnotes and
text boxes are later stories) and renders them as plain paragraphs:

- `\\r` ends a paragraph and `\\x0c` a page or section; `\\x0b` is a line break.
- A field (`\\x13` code `\\x14` result `\\x15`, nesting) keeps its RESULT — what the page
  shows ("3", a link's text) — never its code (`PAGEREF _Toc…`).
- A table cell ends `\\x07` and a row `\\x07\\x07`: cells join with a tab, rows with a line.
- Object anchors (`\\x01` picture, `\\x08` drawing, footnote/comment marks) are dropped;
  `\\x1e` is a non-breaking hyphen, `\\x1f` an optional one.

One address-less `text` segment carries it (the schema's `whole_address: admissible`): a
`.doc` has no stored structure the drafter can address below the whole, so its body is
cited record-wide. OLE2 is read with `xlrd.compdoc` (the `[office]` extra the xls drafter
already uses), so no further dependency.
"""

from __future__ import annotations

import io
import re
import struct
from pathlib import Path
from typing import Any

from corpus import recordbuild, touches
from corpus.draft import DrafterResult, register
from corpus.fingerprint import algos_for_atom, text_fingerprints
from corpus.segments import Segment

_DOC_SCHEMA_ID = "application/application_msword"
_DETECTOR = touches.script_identifier("draft.application/application_msword")

_WORD_IDENT = 0xA5EC
_F_WHICH_TBL_STM = 0x0200
_F_ENCRYPTED = 0x0100
_FC_COMPRESSED = 0x40000000

_DROP = {"\x01", "\x02", "\x03", "\x04", "\x05", "\x08", "\x1f"}


class DocFormatError(ValueError):
    """The bytes are not a Word 97+ document this drafter can read."""


def _compdoc():
    try:
        import xlrd.compdoc as compdoc
    except ImportError as e:
        raise ImportError(
            "doc drafting requires the `[office]` extra. Install with: "
            "uv pip install 'athenaeum[office]'"
        ) from e
    return compdoc


def read_main_text(data: bytes) -> str:
    """The main document story's raw characters (Word's control characters intact).
    Raises `DocFormatError` for anything it cannot read — a truncated FIB or piece table
    included, never a bare `struct.error`."""
    try:
        return _read_main_text(data)
    except (struct.error, IndexError, OverflowError, MemoryError) as e:
        raise DocFormatError(f"malformed Word structures: {e}") from e


def _read_main_text(data: bytes) -> str:
    compdoc = _compdoc()
    try:
        cdoc = compdoc.CompDoc(data, logfile=io.StringIO())
        wd = cdoc.get_named_stream("WordDocument")
    except Exception as e:
        raise DocFormatError(f"not an OLE2 Word document: {e}") from e
    if wd is None or len(wd) < 0x1AA:
        raise DocFormatError("no WordDocument stream (or a truncated FIB)")
    ident, = struct.unpack_from("<H", wd, 0)
    if ident != _WORD_IDENT:
        raise DocFormatError(f"FIB wIdent {ident:#06x} is not Word's {_WORD_IDENT:#06x}")
    flags, = struct.unpack_from("<H", wd, 0x0A)
    if flags & _F_ENCRYPTED:
        raise DocFormatError("the document is encrypted")
    tbl = cdoc.get_named_stream("1Table" if flags & _F_WHICH_TBL_STM else "0Table")
    if tbl is None:
        raise DocFormatError("the FIB names a table stream the file does not hold")
    ccp_text, = struct.unpack_from("<i", wd, 0x4C)
    fc_clx, lcb_clx = struct.unpack_from("<II", wd, 0x1A2)
    clx = tbl[fc_clx:fc_clx + lcb_clx]
    i = 0
    while i < len(clx) and clx[i] == 0x01:  # Prc: property modifiers, skipped
        cb, = struct.unpack_from("<h", clx, i + 1)
        i += 3 + cb
    if i >= len(clx) or clx[i] != 0x02:
        raise DocFormatError("no piece table (Pcdt) in the Clx")
    lcb, = struct.unpack_from("<I", clx, i + 1)
    plc = clx[i + 5:i + 5 + lcb]
    n = (lcb - 4) // 12
    cps = struct.unpack_from(f"<{n + 1}I", plc, 0)
    out: list[str] = []
    for k in range(n):
        fc, = struct.unpack_from("<I", plc, 4 * (n + 1) + 8 * k + 2)
        count = cps[k + 1] - cps[k]
        if fc & _FC_COMPRESSED:
            start = (fc & ~_FC_COMPRESSED) // 2
            out.append(wd[start:start + count].decode("cp1252", errors="replace"))
        else:
            out.append(wd[fc:fc + 2 * count].decode("utf-16-le", errors="replace"))
    return "".join(out)[:max(ccp_text, 0)]


def render_text(raw: str) -> str:
    """Word's character stream as plain paragraphs (module docstring)."""
    shown: list[str] = []
    fields: list[bool] = []  # per open field: True once past its separator (the result)
    for ch in raw:
        if ch == "\x13":
            fields.append(False)
        elif ch == "\x14":
            if fields:
                fields[-1] = True
        elif ch == "\x15":
            if fields:
                fields.pop()
        elif fields and not all(fields):
            continue  # inside a field's code
        elif ch in _DROP:
            continue
        elif ch == "\x1e":
            shown.append("-")
        elif ch == "\x0b":
            shown.append("\n")
        elif ch in ("\r", "\x0c"):
            shown.append("\n\n")
        elif ch == "\x07":
            shown.append("\x07")
        else:
            shown.append(ch)
    text = "".join(shown).replace("\x07\x07", "\n").replace("\x07", "\t")
    lines = [ln.rstrip() for ln in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip() + "\n"


def draft(
    doc_path: Path,
    *,
    build: recordbuild.Build,
    corpus_root: Path | None = None,
    record_id: str | None = None,
    record_metadata: dict[str, Any] | None = None,
    canonical_algo: str | None = None,
    fingerprint: bool | str | list[str] = False,
) -> DrafterResult:
    text_algos = algos_for_atom("text", fingerprint)
    issues: list[dict[str, Any]] = []
    try:
        body = render_text(read_main_text(doc_path.read_bytes()))
    except DocFormatError:
        body = ""
        issues.append({
            "id": "partial-content", "subtype": "empty-body", "severity": "blocking",
            "detector": _DETECTOR, "fields": {},
        })
    segs: list[Segment] = []
    if body.strip():
        segs.append(Segment(atom="text", address=None, body=body,
                            perceptual=text_fingerprints(body, text_algos)))
    recordbuild.add_blocks(build, segs)
    return {"fields": {}, "embeds": [], "issues": issues}


register(_DOC_SCHEMA_ID)(draft)
