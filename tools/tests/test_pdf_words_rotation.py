"""`page=<N>&words` and line geometry land in the DISPLAY frame (`pdf_introspect.display_frame`).

pypdfium2 reports character boxes in PDF user space, before `/Rotate` and offset by the
crop box's origin, while the page's size is the displayed one. A `/Rotate 90` page used to
come back with its axes swapped and boxes off the page; a crop box not at the origin put
words past x = 1. The frame that matters is the render's (the one `page=<N>&bbox=`
crops), so every check here compares a word's box with where pdfium actually draws it.
"""

from __future__ import annotations

import pypdfium2 as pdfium
import pytest

from corpus import pdf_introspect


def _pdf(*, rotate: int = 0, media=(0, 0, 612, 792), crop=None) -> bytes:
    """One page: a wide, short `HEADERWORD` near the user-space top-left, and a body line
    lower down — so a correct box is wide and short in whatever frame the page displays."""
    content = (b"BT /F1 24 Tf 72 720 Td (HEADERWORD) Tj ET "
               b"BT /F1 12 Tf 72 400 Td (body line text) Tj ET")
    extra = b""
    if rotate:
        extra += b" /Rotate %d" % rotate
    if crop:
        extra += b" /CropBox [%d %d %d %d]" % crop
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [%d %d %d %d]%s "
        b"/Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>" % (*media, extra),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
        b"<< /Length %d >>\nstream\n%s\nendstream" % (len(content), content),
    ]
    out = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for i, obj in enumerate(objects, start=1):
        offsets.append(len(out))
        out += f"{i} 0 obj\n".encode() + obj + b"\nendobj\n"
    xref = len(out)
    n = len(objects) + 1
    out += f"xref\n0 {n}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets[1:]:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)


def _ink_box(page, bbox) -> tuple[float, float, float, float] | None:
    """The dark pixels' extent inside `bbox` (display fractions, padded), as fractions of
    the rendered page — where pdfium really draws what the box claims to hold."""
    img = page.render(scale=2).to_pil().convert("L")
    w, h = img.size
    x, y, bw, bh = bbox
    pad = 0.02
    box = (max(0, int((x - pad) * w)), max(0, int((y - pad) * h)),
           min(w, int((x + bw + pad) * w)), min(h, int((y + bh + pad) * h)))
    crop = img.crop(box).point(lambda v: 255 if v < 128 else 0)
    ink = crop.getbbox()
    if ink is None:
        return None
    return ((box[0] + ink[0]) / w, (box[1] + ink[1]) / h,
            (box[0] + ink[2]) / w, (box[1] + ink[3]) / h)


@pytest.mark.parametrize("rotate", [0, 90, 180, 270])
@pytest.mark.parametrize("crop", [None, (40, 30, 562, 772)])
def test_word_boxes_sit_on_the_rendered_ink(tmp_path, rotate, crop):
    src = tmp_path / "p.pdf"
    src.write_bytes(_pdf(rotate=rotate, crop=crop))
    doc = pdfium.PdfDocument(str(src))
    out = pdf_introspect.page_words(doc, 0)
    words = {w["text"]: w["bbox"] for w in out["words"]}
    for bbox in words.values():
        x, y, bw, bh = bbox
        assert x >= 0 and y >= 0 and x + bw <= 1.0001 and y + bh <= 1.0001, bbox
    x, y, bw, bh = words["HEADERWORD"]
    # wide and short in the frame the page displays: the text reads horizontally there
    width_pt, height_pt = bw * out["width_pt"], bh * out["height_pt"]
    if rotate in (0, 180):
        assert width_pt > 3 * height_pt
    else:  # the page was authored upright and turned: the word now runs vertically
        assert height_pt > 3 * width_pt
    ink = _ink_box(doc[0], words["HEADERWORD"])
    assert ink is not None, "no ink inside the word's box"
    ix0, iy0, ix1, iy1 = ink
    tol = 0.02
    assert abs(ix0 - x) < tol and abs(iy0 - y) < tol
    assert abs(ix1 - (x + bw)) < tol and abs(iy1 - (y + bh)) < tol


def test_lines_assemble_in_the_display_frame_on_a_rotated_page(tmp_path):
    """On a /Rotate 90 page whose CONTENT was drawn rotated (so it reads upright on
    screen), lines band on the displayed baseline: one line per printed line."""
    content = (b"q 0 1 -1 0 612 0 cm "  # draw in the landscape frame the display shows
               b"BT /F1 20 Tf 72 560 Td (RUNNING HEAD) Tj ET "
               b"BT /F1 12 Tf 72 300 Td (the body line) Tj ET Q")
    raw = _pdf(rotate=90).replace(
        b"BT /F1 24 Tf 72 720 Td (HEADERWORD) Tj ET BT /F1 12 Tf 72 400 Td (body line text) "
        b"Tj ET", content)
    raw = raw.replace(b"/Length 99", b"/Length %d" % len(content))
    src = tmp_path / "r.pdf"
    src.write_bytes(_rebuild_xref(raw))
    doc = pdfium.PdfDocument(str(src))
    lines = pdf_introspect.assemble_lines(doc[0])
    assert [ln["text"] for ln in lines] == ["RUNNING HEAD", "the body line"]
    head, body = lines
    assert head["y"] < body["y"] and head["x1"] - head["x0"] > 0.1
    assert 0 <= head["y"] < 0.2


def _rebuild_xref(raw: bytes) -> bytes:
    """Recompute the xref after an in-place content edit (offsets moved)."""
    body = raw[:raw.index(b"xref\n")]
    offsets, pos = [], 0
    while (i := body.find(b" 0 obj\n", pos)) != -1:
        start = body.rfind(b"\n", 0, i) + 1
        offsets.append(start)
        pos = i + 1
    n = len(offsets) + 1
    out = bytearray(body)
    xref = len(out)
    out += f"xref\n0 {n}\n".encode() + b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += f"trailer\n<< /Size {n} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF".encode()
    return bytes(out)
